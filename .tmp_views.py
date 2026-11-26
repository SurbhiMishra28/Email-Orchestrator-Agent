import re

src = open("frontend/src/App.jsx", encoding="utf-8").read()

# Views the router knows about vs views that render something.
known = set(re.findall(r'"([a-z_]+)"', src[src.index("const KNOWN_VIEWS"):src.index("const KNOWN_VIEWS") + 400]))
rendered = set(re.findall(r'view==="([a-z_]+)"', src))
nav = set(re.findall(r'id:"([a-z_]+)"', src))

print("KNOWN_VIEWS :", sorted(known))
print("rendered    :", sorted(rendered))
print("nav ids     :", sorted(nav))
print()
print("in nav but never rendered:", sorted(nav - rendered))
print("rendered but not in nav   :", sorted(rendered - nav))
print("in KNOWN but not rendered :", sorted(known - rendered))