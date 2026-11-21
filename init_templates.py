#!/usr/bin/env python3
"""Initialize email templates with Skora Infotech credentials."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import SessionLocal, Template, Settings
from app.services.provisioning import normalize_template_categories

def init_skora_templates():
    """Create Skora Infotech email templates with proper credentials."""
    db = SessionLocal()
    try:
        # Migrate any legacy category spellings first so the guard below sees
        # the canonical "intro" row instead of re-creating a duplicate.
        for tenant_id in [row[0] for row in db.query(Settings.tenant_id).distinct()]:
            if tenant_id is not None:
                normalize_template_categories(db, tenant_id)

        # Check if templates already exist
        existing_pers = db.query(Template).filter(Template.category == "intro").first()
        if existing_pers:
            print("Templates already initialized. Skipping...")
            return
        
        # Skora Infotech settings
        skora_settings = {
            "goal": "grow online presence through websites, marketing and SEO",
            "business_name": "Skora Infotech Pvt Ltd",
            "business_offer": "We work with businesses to grow their online presence through websites, marketing and SEO",
            "footer_text": """This is from Surbhi Mishra from Skora Infotech's team.
Skora Infotech works with businesses to grow their online presence through websites, marketing and SEO.

---
Surbhi Mishra | Sales Manager
Skora Infotech Pvt Ltd
https://skorainfotech.com

Connect with us: 
[Website] | [LinkedIn] | [Twitter]

Unsubscribe | Terms | Privacy

---""",
            "sender_name": "Surbhi Mishra",
            "sender_role": "Sales Manager",
            "company_website": "https://skorainfotech.com",
        }
        
        # Update or create settings
        settings_row = db.query(Settings).first()
        if settings_row:
            for key, value in skora_settings.items():
                setattr(settings_row, key, value)
            db.commit()
            print("Settings updated with Skora Infotech credentials")
        else:
            settings_row = Settings(**skora_settings)
            db.add(settings_row)
            db.commit()
            print("Settings created with Skora Infotech credentials")
        
        # Footer template (used when template-specific footer is needed)
        footer = """This is from {{sender_name}} from {{business_name}}'s team.
{{business_name}} works with businesses to grow their online presence through websites, marketing and SEO.

---
{{sender_name}} | {{sender_role}}
{{business_name}}
{{company_website}}

Connect with us: 
[Website] | [LinkedIn] | [Twitter]

Unsubscribe | Terms | Privacy

---"""

        # Template 1: Personalized/Intro Mail
        personalized_template = Template(
            name="Personalized Mail",
            category="intro",
            subject_template="Quick intro from {{business_name}} about {{goal}}",
            body_template="""Hi {{first_name}},

I hope you're doing well at {{company}}. I'm {{sender_name}} from {{business_name}}. We work with businesses like yours to grow their online presence through websites, marketing and SEO.

I noticed you might be interested in growing your online presence. Would you be open to a quick chat about how we can help?

If yes, I can share some ideas that might work for {{company}}.""",
            footer_template=footer,
            tags=["outreach", "skora", "initial"],
            is_active=True
        )
        db.add(personalized_template)
        db.commit()
        print(f"Created template: {personalized_template.name} (ID: {personalized_template.id})")
        
        # Template 2: Reply Mail
        reply_template = Template(
            name="Reply Mail",
            category="reply",
            subject_template="Re: {{subject}} - Great to hear from you!",
            body_template="""Hi {{first_name}},

Thank you for your response! I'm glad to hear you're interested in learning more about how we can help {{company}} grow its online presence.

{{business_name}} specializes in:
• Professional website development
• Data-driven marketing campaigns
• SEO optimization for higher rankings

I'd love to schedule a quick 15-minute call to discuss how we can help {{company}} achieve its goals.

Looking forward to connecting!""",
            footer_template=footer,
            tags=["reply", "skora", "response"],
            is_active=True
        )
        db.add(reply_template)
        db.commit()
        print(f"Created template: {reply_template.name} (ID: {reply_template.id})")
        
        # Template 3: Follow-ups Mail
        followup_template = Template(
            name="Followups Mail",
            category="followup",
            subject_template="Quick follow-up on {{goal}}",
            body_template="""Hi {{first_name}},

I wanted to follow up on my previous email about how {{business_name}} can help {{company}} grow its online presence through websites, marketing, and SEO.

I understand you're busy, so I'll keep this brief. We've helped similar businesses in the {{industry}} industry increase their online visibility by 200%+ in just a few months.

Would you have 10 minutes this week for a quick conversation?""",
            footer_template=footer,
            tags=["followup", "skora", "nurture"],
            is_active=True
        )
        db.add(followup_template)
        db.commit()
        print(f"Created template: {followup_template.name} (ID: {followup_template.id})")
        
        # Update existing templates to use the footer
        for template in db.query(Template).filter(Template.id != personalized_template.id).all():
            if template.footer_template == "" or template.footer_template is None:
                template.footer_template = footer
                db.commit()
        print("Updated existing templates with footer")
        
        print("\n✓ All templates initialized successfully!")
        print(f"\nSettings configured:")
        print(f"  - Business Name: {skora_settings['business_name']}")
        print(f"  - Sender: {skora_settings['sender_name']} ({skora_settings['sender_role']})")
        print(f"  - Website: {skora_settings['company_website']}")
        
    finally:
        db.close()

if __name__ == "__main__":
    init_skora_templates()