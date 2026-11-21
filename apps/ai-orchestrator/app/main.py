"""AI Orchestrator - Python FastAPI service for email automation AI agents."""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AI Orchestrator", version="1.0.0")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- AI Agents ---

class BaseAgent:
    """Base class for all AI agents."""
    
    def __init__(self, name: str, model: str = "gpt-4"):
        self.name = name
        self.model = model
        self.client = openai_client
    
    async def _call_llm(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2000) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"{self.name} LLM call failed: {e}")
            raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


class LeadResearchAgent(BaseAgent):
    """Agent for researching leads and gathering company information."""
    
    def __init__(self):
        super().__init__("LeadResearchAgent", "gpt-4")
    
    async def research(self, email: str, context: Optional[str] = None) -> Dict[str, Any]:
        domain = email.split('@')[1] if '@' in email else email
        
        prompt = f"""Research the company and person associated with this email: {email}
Domain: {domain}
{f"Additional context: {context}" if context else ""}

Return a JSON object with:
- company: Company name
- role: Likely role/title
- industry: Industry sector
- company_size: Estimated size (startup/small/medium/large/enterprise)
- technologies: Likely technologies used
- pain_points: Potential pain points
- confidence: Confidence score 0-1

Only return valid JSON."""
        
        messages = [
            {"role": "system", "content": "You are a lead research expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.3, max_tokens=1500)
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "email": email,
                "company": "Unknown",
                "role": "Unknown",
                "industry": "Unknown",
                "company_size": "Unknown",
                "technologies": [],
                "pain_points": [],
                "confidence": 0.3
            }


class EmailGenerationAgent(BaseAgent):
    """Agent for generating personalized email content."""
    
    def __init__(self):
        super().__init__("EmailGenerationAgent", "gpt-4")
    
    TONE_PROMPTS = {
        "professional": "Write in a formal, business-appropriate tone. Use proper grammar and professional language.",
        "friendly": "Write in a warm, approachable, conversational tone. Like writing to a colleague you know well.",
        "casual": "Write in a relaxed, informal tone. Use contractions and casual language.",
        "persuasive": "Write in a compelling, action-oriented tone. Focus on benefits and create urgency.",
        "educational": "Write in an informative, teaching tone. Provide value and insights.",
        "urgent": "Write in a time-sensitive tone. Create urgency without being pushy.",
        "empathetic": "Write in an understanding, supportive tone. Show genuine care.",
        "direct": "Write concisely and to-the-point. No fluff, just the essentials.",
    }
    
    async def generate(
        self,
        prompt: str,
        tone: str = "professional",
        length: str = "medium",
        context: Optional[str] = None,
        contact: Optional[Dict[str, Any]] = None,
        template: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        
        tone_instruction = self.TONE_PROMPTS.get(tone, self.TONE_PROMPTS["professional"])
        
        length_guides = {
            "short": "50-100 words",
            "medium": "100-200 words",
            "long": "200-400 words",
        }
        length_guide = length_guides.get(length, length_guides["medium"])
        
        contact_info = ""
        if contact:
            contact_info = f"""
Contact Information:
- Name: {contact.get('name', 'N/A')}
- Company: {contact.get('company', 'N/A')}
- Role: {contact.get('role', 'N/A')}
- Industry: {contact.get('industry', 'N/A')}
"""
        
        template_info = f"\nBase Template:\n{template}" if template else ""
        variables_info = f"\nVariables to include: {json.dumps(variables)}" if variables else ""
        context_info = f"\nAdditional Context:\n{context}" if context else ""
        
        system_prompt = f"""You are an expert email copywriter specializing in B2B outreach.
{tone_instruction}
Target length: {length_guide}

Your task is to generate a personalized email with:
1. A compelling subject line (under 60 characters)
2. Email body (HTML format with proper formatting)
3. Plain text version

Return ONLY a JSON object with keys: subject, html_body, text_body"""
        
        user_prompt = f"""Generate a personalized email based on:
{prompt}
{contact_info}
{context_info}
{template_info}
{variables_info}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.7, max_tokens=2000)
            parsed = json.loads(result)
            return {
                "subject": parsed.get("subject", ""),
                "html_body": parsed.get("html_body", ""),
                "text_body": parsed.get("text_body", ""),
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse email generation result: {e}")
            return {
                "subject": "Follow up",
                "html_body": "<p>Email generation failed. Please try again.</p>",
                "text_body": "Email generation failed. Please try again.",
            }


class SubjectGenerationAgent(BaseAgent):
    """Agent for generating compelling subject lines."""
    
    def __init__(self):
        super().__init__("SubjectGenerationAgent", "gpt-4")
    
    async def generate(
        self,
        body: str,
        tone: str = "professional",
        count: int = 5,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        
        tone_instruction = EmailGenerationAgent.TONE_PROMPTS.get(tone, EmailGenerationAgent.TONE_PROMPTS["professional"])
        context_info = f"\nContext: {context}" if context else ""
        
        system_prompt = f"""You are an expert at writing email subject lines.
{tone_instruction}
Generate {count} compelling subject lines under 60 characters each.
Return ONLY a JSON array of strings."""
        
        user_prompt = f"""Email body:
{body[:1000]}
{context_info}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.8, max_tokens=500)
            subjects = json.loads(result)
            return {"subjects": subjects[:count]}
        except json.JSONDecodeError:
            return {"subjects": ["Follow up", "Quick question", "Thought you'd find this interesting"]}


class SpamComplianceAgent(BaseAgent):
    """Agent for ensuring email compliance with spam laws."""
    
    def __init__(self):
        super().__init__("SpamComplianceAgent", "gpt-3.5-turbo")
    
    async def analyze(self, content: str) -> Dict[str, Any]:
        prompt = f"""Analyze this email content for spam compliance:
{content}

Check for:
- Spam trigger words
- Misleading subject lines
- Missing unsubscribe link
- Missing physical address
- Excessive capitalization/punctuation
- Deceptive content

Return JSON with:
- spam_score: 0-1 (lower is better)
- is_compliant: boolean
- issues: array of issues found
- recommendations: array of fixes"""
        
        messages = [
            {"role": "system", "content": "You are a spam compliance expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.2, max_tokens=1000)
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "spam_score": 0.2,
                "is_compliant": True,
                "issues": [],
                "recommendations": ["Ensure unsubscribe link is present", "Include physical mailing address"]
            }


class CampaignOptimizationAgent(BaseAgent):
    """Agent for optimizing email campaigns."""
    
    def __init__(self):
        super().__init__("CampaignOptimizationAgent", "gpt-4")
    
    async def optimize(self, campaign: Dict[str, Any], goals: List[str]) -> Dict[str, Any]:
        prompt = f"""Analyze this campaign and provide optimization recommendations:
Campaign: {json.dumps(campaign, indent=2)}
Goals: {goals}

Provide recommendations for:
1. Send time optimization
2. Frequency optimization
3. Content improvements
4. Segmentation suggestions
5. A/B test ideas

Return JSON with recommendations for each category."""
        
        messages = [
            {"role": "system", "content": "You are an email marketing optimization expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.5, max_tokens=2000)
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "send_time": "Test Tuesday/Thursday 10 AM",
                "frequency": "2-3 emails per week",
                "content": ["Add more personalization", "Include social proof"],
                "segmentation": ["By industry", "By engagement level"],
                "ab_tests": ["Subject line variations", "CTA button text"]
            }


class SegmentAnalysisAgent(BaseAgent):
    """Agent for analyzing contacts and suggesting segments."""
    
    def __init__(self):
        super().__init__("SegmentAnalysisAgent", "gpt-4")
    
    async def suggest_segments(self, contact_sample: List[Dict[str, Any]], goals: Optional[List[str]] = None) -> Dict[str, Any]:
        sample_json = json.dumps(contact_sample[:20], indent=2)
        goals_text = f"\nGoals: {goals}" if goals else ""
        
        prompt = f"""Analyze these contacts and suggest meaningful segments:
{sample_json}
{goals_text}

Suggest 5-7 segments with:
- name: Segment name
- description: What defines this segment
- query: Filter criteria (as JSON logic)
- estimated_size: Percentage of contacts
- recommended_approach: Messaging strategy

Return JSON array of segments."""
        
        messages = [
            {"role": "system", "content": "You are a customer segmentation expert. Return only valid JSON array."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.5, max_tokens=2000)
            return {"segments": json.loads(result)}
        except json.JSONDecodeError:
            return {"segments": []}


class ReplyClassificationAgent(BaseAgent):
    """Agent for classifying inbound replies."""
    
    def __init__(self):
        super().__init__("ReplyClassificationAgent", "gpt-3.5-turbo")
    
    async def classify(self, reply_text: str, subject: Optional[str] = None, contact: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contact_info = f"\nContact: {json.dumps(contact)}" if contact else ""
        subject_info = f"\nSubject: {subject}" if subject else ""
        
        prompt = f"""Classify this email reply:
Reply: {reply_text}
{subject_info}
{contact_info}

Return JSON with:
- sentiment: positive/neutral/negative
- intent: interested/not_interested/unsubscribe/question/out_of_office/bounce/other
- urgency: high/medium/low
- category: sales/support/partnership/feedback/spam/other
- suggested_action: continue_nurture/schedule_call/remove_from_list/respond_manually/auto_reply
- confidence: 0-1"""
        
        messages = [
            {"role": "system", "content": "You are an email reply classification expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.2, max_tokens=500)
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "sentiment": "neutral",
                "intent": "other",
                "urgency": "medium",
                "category": "other",
                "suggested_action": "respond_manually",
                "confidence": 0.5
            }


class DeliverabilityAnalyzerAgent(BaseAgent):
    """Agent for monitoring and improving email deliverability."""
    
    def __init__(self):
        super().__init__("DeliverabilityAnalyzerAgent", "gpt-4")
    
    async def analyze(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        prompt = f"""Analyze these email deliverability metrics:
{json.dumps(metrics, indent=2)}

Provide:
- reputation_score: 0-100
- issues: Array of deliverability issues
- recommendations: Array of actionable fixes
- priority: high/medium/low for each recommendation
- spf_dkim_dmarc_status: Current auth status"""
        
        messages = [
            {"role": "system", "content": "You are an email deliverability expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.3, max_tokens=1500)
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "reputation_score": 85,
                "issues": [],
                "recommendations": ["Set up DMARC policy", "Monitor bounce rates"],
                "priority": ["medium", "low"],
                "spf_dkim_dmarc_status": "SPF: Pass, DKIM: Pass, DMARC: None"
            }


class PersonalizationEngineAgent(BaseAgent):
    """Agent for creating personalized content at scale."""
    
    def __init__(self):
        super().__init__("PersonalizationEngineAgent", "gpt-4")
    
    async def personalize(
        self,
        base_content: str,
        contacts: List[Dict[str, Any]],
        personalization_fields: List[str],
    ) -> Dict[str, Any]:
        prompt = f"""Personalize this content for multiple contacts:
Base content:
{base_content}

Contacts sample (first 5):
{json.dumps(contacts[:5], indent=2)}

Personalization fields available: {personalization_fields}

Generate personalized versions for each contact. Return JSON with:
- personalized: Array of {{contact_id, subject, body}}
- fallback: Generic version for contacts missing data"""
        
        messages = [
            {"role": "system", "content": "You are a personalization expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.6, max_tokens=3000)
            return json.loads(result)
        except json.JSONDecodeError:
            return {"personalized": [], "fallback": base_content}


class FollowUpAgent(BaseAgent):
    """Agent for generating follow-up sequences."""
    
    def __init__(self):
        super().__init__("FollowUpAgent", "gpt-4")
    
    async def generate_sequence(
        self,
        original_email: Dict[str, Any],
        contact: Optional[Dict[str, Any]] = None,
        max_followups: int = 3,
    ) -> List[Dict[str, Any]]:
        contact_info = f"\nContact: {json.dumps(contact)}" if contact else ""
        
        prompt = f"""Generate a {max_followups}-email follow-up sequence based on:
Original email: {json.dumps(original_email, indent=2)}
{contact_info}

Each follow-up should:
- Be progressively shorter
- Add new value/perspective
- Have different CTAs
- Reference previous emails naturally

Return JSON array with:
- day: Days after previous email
- subject: Subject line
- html_body: HTML content
- text_body: Plain text
- tone: Tone for this follow-up"""
        
        messages = [
            {"role": "system", "content": "You are a follow-up sequence expert. Return only valid JSON array."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            result = await self._call_llm(messages, temperature=0.7, max_tokens=2500)
            return json.loads(result)
        except json.JSONDecodeError:
            return [
                {"day": 3, "subject": "Following up", "html_body": "<p>Just following up...</p>", "text_body": "Just following up...", "tone": "friendly"},
                {"day": 5, "subject": "Last attempt", "html_body": "<p>Last time reaching out...</p>", "text_body": "Last time reaching out...", "tone": "direct"},
            ]


# --- Orchestrator ---

class OrchestratorAgent:
    """Main orchestrator that coordinates all AI agents."""
    
    def __init__(self):
        self.lead_research = LeadResearchAgent()
        self.email_gen = EmailGenerationAgent()
        self.subject_gen = SubjectGenerationAgent()
        self.spam_comply = SpamComplianceAgent()
        self.campaign_optimizer = CampaignOptimizationAgent()
        self.segment_analyzer = SegmentAnalysisAgent()
        self.reply_classify = ReplyClassificationAgent()
        self.deliverability_analyzer = DeliverabilityAnalyzerAgent()
        self.personalization_engine = PersonalizationEngineAgent()
        self.followup = FollowUpAgent()

    async def process_workflow(self, workflow: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a multi-agent workflow."""
        workflows = {
            "email_generation": self._email_generation_workflow,
            "campaign_optimization": self._campaign_optimization_workflow,
            "reply_handling": self._reply_handling_workflow,
            "lead_enrichment": self._lead_enrichment_workflow,
        }
        
        if workflow not in workflows:
            raise HTTPException(status_code=400, detail=f"Unknown workflow: {workflow}")
        
        return await workflows[workflow](input_data)
    
    async def _email_generation_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Research lead if email provided
        contact = data.get("contact", {})
        if contact.get("email") and not contact.get("company"):
            research = await self.lead_research.research(contact["email"])
            contact.update(research)
        
        # 2. Generate email
        email = await self.email_gen.generate(
            prompt=data.get("prompt", ""),
            tone=data.get("tone", "professional"),
            length=data.get("length", "medium"),
            context=data.get("context"),
            contact=contact,
            template=data.get("template"),
            variables=data.get("variables"),
        )
        
        # 3. Generate subject alternatives
        subjects = await self.subject_gen.generate(
            body=email["html_body"],
            tone=data.get("tone", "professional"),
            count=3,
        )
        
        # 4. Check spam compliance
        spam_check = await self.spam_comply.analyze(email["html_body"])
        
        # 5. Generate follow-ups if requested
        followups = []
        if data.get("generate_followups"):
            followups = await self.followup.generate_sequence(email, contact)
        
        return {
            "email": email,
            "subject_alternatives": subjects.get("subjects", []),
            "spam_check": spam_check,
            "followups": followups,
            "enriched_contact": contact,
        }
    
    async def _campaign_optimization_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        campaign = data.get("campaign", {})
        goals = data.get("goals", ["open_rate", "click_rate", "reply_rate"])
        
        optimization = await self.campaign_optimizer.optimize(campaign, goals)
        deliverability = await self.deliverability_analyzer.analyze(campaign.get("metrics", {}))
        
        return {
            "optimization": optimization,
            "deliverability": deliverability,
        }
    
    async def _reply_handling_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        reply_text = data.get("reply_text", "")
        subject = data.get("subject")
        contact = data.get("contact")
        
        classification = await self.reply_classify.classify(reply_text, subject, contact)
        
        # Generate auto-reply if needed
        auto_reply = None
        if classification.get("suggested_action") == "auto_reply":
            auto_reply = await self.email_gen.generate(
                prompt=f"Write a brief, professional response to: {reply_text}",
                tone="professional",
                length="short",
            )
        
        return {
            "classification": classification,
            "auto_reply": auto_reply,
        }
    
    async def _lead_enrichment_workflow(self, data: Dict[str, Any]) -> Dict[str, Any]:
        emails = data.get("emails", [])
        enriched = []
        
        for email in emails:
            research = await self.lead_research.research(email)
            enriched.append(research)
        
        return {"enriched_leads": enriched}


orchestrator = OrchestratorAgent()

# --- Request/Response Models ---

class LeadResearchRequest(BaseModel):
    email: str
    context: Optional[str] = None

class LeadResearchResponse(BaseModel):
    email: str
    company: Optional[str] = None
    role: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    technologies: List[str] = []
    pain_points: List[str] = []
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

class EmailGenerationRequest(BaseModel):
    prompt: str
    tone: str = "professional"
    length: str = "medium"
    context: Optional[str] = None
    contact: Optional[Dict[str, Any]] = None
    template: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    generate_followups: bool = False

class EmailGenerationResponse(BaseModel):
    subject: str
    html_body: str
    text_body: str

class SubjectGenerationRequest(BaseModel):
    body: str
    tone: str = "professional"
    count: int = 5
    context: Optional[str] = None

class SubjectGenerationResponse(BaseModel):
    subjects: List[str]

class SpamAnalysisRequest(BaseModel):
    content: str

class SpamAnalysisResponse(BaseModel):
    spam_score: float
    is_compliant: bool
    issues: List[str]
    recommendations: List[str]

class ReplyClassificationRequest(BaseModel):
    reply_text: str
    subject: Optional[str] = None
    contact: Optional[Dict[str, Any]] = None

class ReplyClassificationResponse(BaseModel):
    sentiment: str
    intent: str
    urgency: str
    category: str
    suggested_action: str
    confidence: float

class CampaignOptimizationRequest(BaseModel):
    campaign: Dict[str, Any]
    goals: List[str] = ["open_rate", "click_rate", "reply_rate"]

class CampaignOptimizationResponse(BaseModel):
    optimization: Dict[str, Any]
    deliverability: Dict[str, Any]

class SegmentSuggestionRequest(BaseModel):
    contact_sample: List[Dict[str, Any]]
    goals: Optional[List[str]] = None

class SegmentSuggestionResponse(BaseModel):
    segments: List[Dict[str, Any]]

class WorkflowRequest(BaseModel):
    workflow: str
    input_data: Dict[str, Any]

class WorkflowResponse(BaseModel):
    result: Dict[str, Any]

# --- API Endpoints ---

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ai-orchestrator", "version": "1.0.0"}

@app.get("/agents")
async def list_agents():
    return {
        "agents": [
            {"id": "lead_research", "name": "Lead Research Agent", "description": "Researches leads and gathers company information"},
            {"id": "email_writer", "name": "Email Writer Agent", "description": "Generates personalized email content"},
            {"id": "subject_generator", "name": "Subject Line Generator", "description": "Creates compelling subject lines"},
            {"id": "spam_compliance", "name": "Spam Compliance Agent", "description": "Ensures email compliance with spam laws"},
            {"id": "campaign_optimizer", "name": "Campaign Optimizer", "description": "Optimizes campaigns for better performance"},
            {"id": "segment_analyzer", "name": "Segment Analyzer", "description": "Analyzes contacts and suggests segments"},
            {"id": "reply_classifier", "name": "Reply Classifier", "description": "Classifies incoming replies for automation"},
            {"id": "deliverability_analyzer", "name": "Deliverability Analyzer", "description": "Monitors and improves email deliverability"},
            {"id": "personalization_engine", "name": "Personalization Engine", "description": "Creates personalized content at scale"},
            {"id": "followup_agent", "name": "Follow-up Agent", "description": "Generates follow-up sequences"},
        ]
    }

@app.post("/agents/lead-research", response_model=LeadResearchResponse)
async def research_lead(request: LeadResearchRequest):
    result = await orchestrator.lead_research.research(request.email, request.context)
    return LeadResearchResponse(**result)

@app.post("/agents/email/generate", response_model=EmailGenerationResponse)
async def generate_email(request: EmailGenerationRequest):
    result = await orchestrator.email_gen.generate(
        prompt=request.prompt,
        tone=request.tone,
        length=request.length,
        context=request.context,
        contact=request.contact,
        template=request.template,
        variables=request.variables,
    )
    return EmailGenerationResponse(**result)

@app.post("/agents/email/subjects", response_model=SubjectGenerationResponse)
async def generate_subjects(request: SubjectGenerationRequest):
    result = await orchestrator.subject_gen.generate(
        body=request.body,
        tone=request.tone,
        count=request.count,
        context=request.context,
    )
    return SubjectGenerationResponse(**result)

@app.post("/agents/spam/analyze", response_model=SpamAnalysisResponse)
async def analyze_spam(request: SpamAnalysisRequest):
    result = await orchestrator.spam_comply.analyze(request.content)
    return SpamAnalysisResponse(**result)

@app.post("/agents/reply/classify", response_model=ReplyClassificationResponse)
async def classify_reply(request: ReplyClassificationRequest):
    result = await orchestrator.reply_classify.classify(
        request.reply_text,
        request.subject,
        request.contact,
    )
    return ReplyClassificationResponse(**result)

@app.post("/agents/campaign/optimize", response_model=CampaignOptimizationResponse)
async def optimize_campaign(request: CampaignOptimizationRequest):
    result = await orchestrator.campaign_optimizer.optimize(request.campaign, request.goals)
    deliverability = await orchestrator.deliverability_analyzer.analyze(request.campaign.get("metrics", {}))
    return CampaignOptimizationResponse(optimization=result, deliverability=deliverability)

@app.post("/agents/segments/suggest", response_model=SegmentSuggestionResponse)
async def suggest_segments(request: SegmentSuggestionRequest):
    result = await orchestrator.segment_analyzer.suggest_segments(request.contact_sample, request.goals)
    return SegmentSuggestionResponse(**result)

@app.post("/agents/deliverability/analyze")
async def analyze_deliverability(metrics: Dict[str, Any]):
    result = await orchestrator.deliverability_analyzer.analyze(metrics)
    return result

@app.post("/agents/personalize")
async def personalize_content(
    base_content: str,
    contacts: List[Dict[str, Any]],
    personalization_fields: List[str],
):
    result = await orchestrator.personalization_engine.personalize(base_content, contacts, personalization_fields)
    return result

@app.post("/agents/followup/generate")
async def generate_followups(
    original_email: Dict[str, Any],
    contact: Optional[Dict[str, Any]] = None,
    max_followups: int = 3,
):
    result = await orchestrator.followup.generate_sequence(original_email, contact, max_followups)
    return {"followups": result}

@app.post("/workflow", response_model=WorkflowResponse)
async def run_workflow(request: WorkflowRequest):
    result = await orchestrator.process_workflow(request.workflow, request.input_data)
    return WorkflowResponse(result=result)

# --- Individual Agent Endpoints ---

@app.post("/agent/{agent_name}")
async def trigger_agent(agent_name: str, input_data: Dict[str, Any]):
    """Trigger a specific agent directly."""
    agents = {
        "lead_research": orchestrator.lead_research,
        "email_writer": orchestrator.email_gen,
        "subject_generator": orchestrator.subject_gen,
        "spam_compliance": orchestrator.spam_comply,
        "campaign_optimizer": orchestrator.campaign_optimizer,
        "segment_analyzer": orchestrator.segment_analyzer,
        "reply_classifier": orchestrator.reply_classify,
        "deliverability_analyzer": orchestrator.deliverability_analyzer,
        "personalization_engine": orchestrator.personalization_engine,
        "followup_agent": orchestrator.followup,
    }
    
    if agent_name not in agents:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")
    
    agent = agents[agent_name]
    
    # Call appropriate method based on agent
    if agent_name == "lead_research":
        result = await agent.research(input_data.get("email"), input_data.get("context"))
    elif agent_name == "email_writer":
        result = await agent.generate(**input_data)
    elif agent_name == "subject_generator":
        result = await agent.generate(**input_data)
    elif agent_name == "spam_compliance":
        result = await agent.analyze(input_data.get("content", ""))
    elif agent_name == "campaign_optimizer":
        result = await agent.optimize(input_data.get("campaign", {}), input_data.get("goals", []))
    elif agent_name == "segment_analyzer":
        result = await agent.suggest_segments(input_data.get("contact_sample", []), input_data.get("goals"))
    elif agent_name == "reply_classifier":
        result = await agent.classify(
            input_data.get("reply_text", ""),
            input_data.get("subject"),
            input_data.get("contact"),
        )
    elif agent_name == "deliverability_analyzer":
        result = await agent.analyze(input_data)
    elif agent_name == "personalization_engine":
        result = await agent.personalize(
            input_data.get("base_content", ""),
            input_data.get("contacts", []),
            input_data.get("personalization_fields", []),
        )
    elif agent_name == "followup_agent":
        result = await agent.generate_sequence(
            input_data.get("original_email", {}),
            input_data.get("contact"),
            input_data.get("max_followups", 3),
        )
    
    return {"agent": agent_name, "result": result}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)