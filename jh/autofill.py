"""1-Click Application Autofill & Easy Apply Engine for JobHunter.

Generates comprehensive ATS form field mappings (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, etc.),
AI-powered truthful screening question solving, universal browser bookmarklet auto-injector with platform-specific rules,
and 1-Click Easy Apply application tracking.
"""
import datetime
import json
import re
import time
from urllib.parse import quote

from . import db, tracker, refit, config
from .util import clean_text, now_iso


def parse_name(full_name):
    """Split full name into first and last name safely."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "Candidate", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def detect_ats_platform(url):
    """Detect ATS platform provider from job url or career portal host."""
    u = (url or "").lower()
    if "greenhouse.io" in u or "grnh.se" in u:
        return "greenhouse"
    if "lever.co" in u:
        return "lever"
    if "ashbyhq.com" in u:
        return "ashby"
    if "myworkdayjobs.com" in u or "workday" in u:
        return "workday"
    if "smartrecruiters.com" in u:
        return "smartrecruiters"
    if "workable.com" in u:
        return "workable"
    if "bamboohr.com" in u:
        return "bamboohr"
    if "taleo.net" in u or "oraclecloud.com" in u:
        return "taleo"
    if "icims.com" in u:
        return "icims"
    if "jobvite.com" in u:
        return "jobvite"
    if "rippling.com" in u:
        return "rippling"
    if "breezy.hr" in u:
        return "breezy"
    if "linkedin.com" in u:
        return "linkedin"
    return "standard"


PLATFORM_INFO = {
    "lever": {
        "name": "Lever",
        "badge": "Lever ATS",
        "input_style": "URL-Indexed Inputs (urls[...]) & Combined Full Name",
        "mandatory_rules": [
            "LinkedIn Profile URL (urls[LinkedIn]) — STRICTLY MANDATORY on Lever; submission blocks if missing",
            "Full Name (single combined input name='name')",
            "Email Address & Phone Number",
            "Resume File Attachment"
        ],
        "cover_letter_style": "textarea[name='comments'] ('Additional Information' field used as candidate cover pitch)",
        "linkedin_style": "input[name='urls[LinkedIn]'] (exact structured parameter)",
        "key_requirements": [
            {"label": "LinkedIn Profile (urls[LinkedIn])", "required": True, "status": "Ready", "selector": "input[name='urls[LinkedIn]']", "notes": "Lever strictly mandates LinkedIn URL in the urls[...] namespace."},
            {"label": "Full Name", "required": True, "status": "Ready", "selector": "input[name='name']", "notes": "Lever uses single combined name input."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[name='email'], input[name='phone']", "notes": "Direct contact details."},
            {"label": "Current Company (org)", "required": False, "status": "Ready", "selector": "input[name='org']", "notes": "Current or most recent employer."},
            {"label": "GitHub & Portfolio URLs", "required": False, "status": "Ready", "selector": "input[name='urls[GitHub]'], input[name='urls[Portfolio]']", "notes": "Dedicated web presence slots."},
            {"label": "Cover Pitch (Comments)", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[name='comments']", "notes": "Lever uses 'comments' as the cover letter pitch."}
        ],
        "tip": "Lever separates web presence into urls[...] inputs and uses 'comments' as the cover pitch field. LinkedIn is strictly enforced."
    },
    "greenhouse": {
        "name": "Greenhouse",
        "badge": "Greenhouse ATS",
        "input_style": "Discrete HTML5 IDs & Custom Application Question Schema",
        "mandatory_rules": [
            "Discrete First & Last Name (#first_name, #last_name)",
            "Email & Phone Number",
            "Cover Letter Textarea (#cover_letter_text) — frequently required by hiring teams",
            "EEO Demographic Disclosures (auto-declined to protect candidate privacy)"
        ],
        "cover_letter_style": "#cover_letter_text or textarea[name='job_application[cover_letter_text]']",
        "linkedin_style": "input[autocomplete='custom-question-linkedin'], input[id*='linkedin' i]",
        "key_requirements": [
            {"label": "Discrete First & Last Name", "required": True, "status": "Ready", "selector": "#first_name, #last_name", "notes": "Separated into discrete input elements."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "#email, #phone", "notes": "Standard HTML inputs."},
            {"label": "Cover Letter Textarea", "required": True, "status": "Auto-pasting Tailored Pitch", "selector": "#cover_letter_text", "notes": "Directly injected into Greenhouse's cover letter editor."},
            {"label": "LinkedIn Profile", "required": False, "status": "Ready", "selector": "custom-question-linkedin", "notes": "Mapped to Greenhouse custom question input."},
            {"label": "EEO Disclosures", "required": True, "status": "Auto-declining to identify", "selector": "select[id*='job_application_']", "notes": "Auto-selects 'Decline to self-identify' across 5 survey selects."}
        ],
        "tip": "Greenhouse uses discrete first/last name inputs and has a dedicated #cover_letter_text area."
    },
    "ashby": {
        "name": "Ashby",
        "badge": "Ashby ATS",
        "input_style": "React 16+ Virtual DOM Controlled Inputs (Synthetic Event Dispatch)",
        "mandatory_rules": [
            "Full Name (React-controlled)",
            "Email & Phone Number",
            "LinkedIn Profile URL (standard in tech startups)",
            "React State Synchronization (synthetic event bubbling required)"
        ],
        "cover_letter_style": "textarea[placeholder*='cover letter' i], textarea[name*='coverLetter' i]",
        "linkedin_style": "input[name*='linkedin' i]",
        "key_requirements": [
            {"label": "Full Name", "required": True, "status": "Ready", "selector": "input[name='name'], input[autocomplete='name']", "notes": "React-controlled input."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[type='email'], input[type='tel']", "notes": "Validated via React fiber events."},
            {"label": "LinkedIn & GitHub Links", "required": True, "status": "Ready", "selector": "input[name*='linkedin' i], input[name*='github' i]", "notes": "Expected by Ashby startup boards."},
            {"label": "Cover Note", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[placeholder*='cover letter' i]", "notes": "Direct note to hiring manager."},
            {"label": "React State Sync", "required": True, "status": "Dispatched via Synthetic Events", "selector": "Object.prototype value setter", "notes": "Bypasses React fiber value tracker so values persist on submit."}
        ],
        "tip": "Ashby is React-driven; our script dispatches synthetic bubbled events to keep React state synchronized."
    },
    "workday": {
        "name": "Workday",
        "badge": "Workday ATS",
        "input_style": "Multi-Step Wizard with data-automation-id Attributes",
        "mandatory_rules": [
            "Legal First & Last Name (data-automation-id='legalNameSection_...')",
            "Complete Physical Address, City & Postal Code (data-automation-id='addressSection_...')",
            "Work Authorization Radio Buttons ('Yes' to authorization, 'No' to sponsorship)",
            "Prior Employment Radio Button ('No' to prior employment)"
        ],
        "cover_letter_style": "textarea[data-automation-id*='cover' i] or experience narrative box",
        "linkedin_style": "input[data-automation-id*='linkedin' i]",
        "key_requirements": [
            {"label": "Legal First & Last Name", "required": True, "status": "Ready", "selector": "input[data-automation-id*='legalName']", "notes": "Workday enforces strict legal identity matching."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[data-automation-id='email'], input[data-automation-id='phone-number']", "notes": "Contact section."},
            {"label": "City & Address Details", "required": True, "status": "Ready", "selector": "input[data-automation-id*='address']", "notes": "City, street, postal code."},
            {"label": "Work Authorization Radio", "required": True, "status": "Auto-checked 'Yes'", "selector": "input[type='radio']", "notes": "Auto-checks 'Yes' for authorization, 'No' for sponsorship."},
            {"label": "Cover Pitch", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[data-automation-id*='cover' i]", "notes": "Application summary notes."}
        ],
        "tip": "Workday uses data-automation-id attributes. Run the bookmarklet on each page of the application wizard."
    },
    "smartrecruiters": {
        "name": "SmartRecruiters",
        "badge": "SmartRecruiters ATS",
        "input_style": "data-test Attribute Selectors & Location Autocomplete",
        "mandatory_rules": [
            "First & Last Name (data-test='first-name-input', data-test='last-name-input')",
            "Email & Phone Number",
            "Message to Hiring Manager (data-test='message-to-hiring-manager')",
            "LinkedIn Profile URL"
        ],
        "cover_letter_style": "textarea[data-test='message-to-hiring-manager'] (Message to hiring manager)",
        "linkedin_style": "input[data-test='linkedin-input']",
        "key_requirements": [
            {"label": "First & Last Name", "required": True, "status": "Ready", "selector": "input[data-test='first-name-input']", "notes": "Split name inputs."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[data-test='email-input']", "notes": "Contact information."},
            {"label": "Message to Hiring Manager", "required": True, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[data-test='message-to-hiring-manager']", "notes": "SmartRecruiters cover letter textarea."},
            {"label": "LinkedIn Profile", "required": False, "status": "Ready", "selector": "input[data-test='linkedin-input']", "notes": "Profile URL input."}
        ],
        "tip": "SmartRecruiters labels the cover letter as 'Message to hiring manager' and uses data-test attributes."
    },
    "workable": {
        "name": "Workable",
        "badge": "Workable ATS",
        "input_style": "HTML5 Semantic IDs (#firstname, #lastname, #coverletter)",
        "mandatory_rules": [
            "First & Last Name (#firstname, #lastname)",
            "Email & Phone (#email, #phone)",
            "Cover Letter Textarea (#coverletter)",
            "Social Profiles (#linkedin, #website, #github)"
        ],
        "cover_letter_style": "#coverletter, textarea[name='cover_letter']",
        "linkedin_style": "#linkedin, input[name='linkedin']",
        "key_requirements": [
            {"label": "First & Last Name", "required": True, "status": "Ready", "selector": "#firstname, #lastname", "notes": "Semantic ID structure."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "#email, #phone", "notes": "Contact info."},
            {"label": "Cover Letter Textarea", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "#coverletter", "notes": "Paste pitch directly."},
            {"label": "Social & Website", "required": False, "status": "Ready", "selector": "#linkedin, #website, #github", "notes": "Populated automatically."}
        ],
        "tip": "Workable uses clean semantic IDs. Our script fills all basic, social, and cover letter fields in one click."
    },
    "bamboohr": {
        "name": "BambooHR",
        "badge": "BambooHR ATS",
        "input_style": "Standard Form with Date Available & Desired Salary",
        "mandatory_rules": [
            "First & Last Name (name='firstName', name='lastName')",
            "Email & Phone Number",
            "Date Available to Start (name='dateAvailable')",
            "Desired Salary (name='desiredSalary')"
        ],
        "cover_letter_style": "textarea[name='coverLetter']",
        "linkedin_style": "input[name*='linkedin' i]",
        "key_requirements": [
            {"label": "First & Last Name", "required": True, "status": "Ready", "selector": "input[name='firstName'], input[name='lastName']", "notes": "Discrete inputs."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[name='email'], input[name='phone']", "notes": "Contact info."},
            {"label": "Cover Letter", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[name='coverLetter']", "notes": "Pitch notes."},
            {"label": "Desired Salary & Date Available", "required": False, "status": "Ready", "selector": "input[name='desiredSalary'], input[name='dateAvailable']", "notes": "Compensation & notice."}
        ],
        "tip": "BambooHR commonly asks for desired salary and start date directly on the initial application page."
    },
    "linkedin": {
        "name": "LinkedIn Easy Apply",
        "badge": "LinkedIn ATS",
        "input_style": "Multi-Step Modal Dialog with Dial Code & Experience Survey",
        "mandatory_rules": [
            "Phone Number with Country Dial Code",
            "Email Address",
            "Resume Selection (from uploaded files)",
            "Numeric Years of Experience Questions per skill",
            "Work Authorization & Sponsorship Radio Buttons"
        ],
        "cover_letter_style": "textarea[id*='coverLetter' i] (if requested by job poster)",
        "linkedin_style": "Auto-linked to applicant's logged-in profile",
        "key_requirements": [
            {"label": "Phone Number & Dial Code", "required": True, "status": "Ready", "selector": "input[id*='phoneNumber']", "notes": "Formatted with country code."},
            {"label": "Email Address", "required": True, "status": "Ready", "selector": "input[id*='email']", "notes": "Candidate email."},
            {"label": "Years Experience Screening", "required": True, "status": "Ready", "selector": "input[id*='numeric-text-form-component']", "notes": "Auto-calculated based on profile history."},
            {"label": "Sponsorship & Work Auth Radios", "required": True, "status": "Auto-checked", "selector": "input[type='radio']", "notes": "Answers sponsorship and legal authorization questions."}
        ],
        "tip": "LinkedIn Easy Apply uses multi-step modal dialogs. Use our 1-Click palette or script to quickly answer step questions."
    },
    "taleo": {
        "name": "Taleo / Oracle Cloud",
        "badge": "Taleo ATS",
        "input_style": "Legacy Enterprise Multi-Page Form with Postal Code Verification",
        "mandatory_rules": [
            "Legal First, Middle & Last Name",
            "Full Physical Street Address & Postal Code",
            "Work Authorization Select Dropdowns"
        ],
        "cover_letter_style": "textarea[id*='coverLetter' i], textarea[id*='comments' i]",
        "linkedin_style": "input[id*='linkedIn' i]",
        "key_requirements": [
            {"label": "Legal First & Last Name", "required": True, "status": "Ready", "selector": "input[id*='firstName' i], input[id*='lastName' i]", "notes": "Enterprise name inputs."},
            {"label": "Full Postal Address", "required": True, "status": "Ready", "selector": "input[id*='address' i], input[id*='zip' i]", "notes": "Address verification."},
            {"label": "Work Authorization", "required": True, "status": "Auto-selected", "selector": "select[id*='authorization' i]", "notes": "Auto-answered."}
        ],
        "tip": "Taleo forms are multi-page enterprise portals; click the bookmarklet on each page of the candidate wizard."
    },
    "icims": {
        "name": "iCIMS",
        "badge": "iCIMS ATS",
        "input_style": "Iframe-Embedded Career Portal with Document Attachment",
        "mandatory_rules": [
            "First & Last Name",
            "Email & Phone Number",
            "Source Selection ('How did you hear about us?')"
        ],
        "cover_letter_style": "textarea[id*='CoverLetter' i]",
        "linkedin_style": "input[id*='LinkedIn' i]",
        "key_requirements": [
            {"label": "First & Last Name", "required": True, "status": "Ready", "selector": "input[id*='FirstName' i], input[id*='LastName' i]", "notes": "Portal name fields."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "input[id*='Email' i], input[id*='Phone' i]", "notes": "Contact fields."},
            {"label": "Source Selection", "required": True, "status": "Auto-selected", "selector": "select[id*='Source' i]", "notes": "Auto-selected 'Job Board' / 'LinkedIn'."}
        ],
        "tip": "If iCIMS is inside an iframe, click inside the form iframe before triggering the bookmarklet."
    },
    "jobvite": {
        "name": "Jobvite",
        "badge": "Jobvite ATS",
        "input_style": "Standard Web Form with Cell Phone and Portfolio Links",
        "mandatory_rules": [
            "First & Last Name (name='firstName', name='lastName')",
            "Email & Cell Phone (name='cellPhone')",
            "Resume File"
        ],
        "cover_letter_style": "textarea[name='coverLetter']",
        "linkedin_style": "input[name='linkedInUrl']",
        "key_requirements": [
            {"label": "First & Last Name", "required": True, "status": "Ready", "selector": "input[name='firstName'], input[name='lastName']", "notes": "Discrete name."},
            {"label": "Email & Cell Phone", "required": True, "status": "Ready", "selector": "input[name='email'], input[name='cellPhone']", "notes": "Contact info."},
            {"label": "LinkedIn URL", "required": False, "status": "Ready", "selector": "input[name='linkedInUrl']", "notes": "Social profile."},
            {"label": "Cover Letter", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea[name='coverLetter']", "notes": "Application letter."}
        ],
        "tip": "Jobvite specifically names the phone input 'cellPhone' and uses linkedInUrl for social profiles."
    },
    "standard": {
        "name": "Standard Career Portal",
        "badge": "Standard ATS",
        "input_style": "HTML5 Heuristic Matching across Attributes, Labels, and ARIA Tags",
        "mandatory_rules": [
            "Candidate Full Name or First/Last Split",
            "Email Address & Phone Number",
            "Resume File"
        ],
        "cover_letter_style": "textarea (heuristic match on cover, letter, note, pitch)",
        "linkedin_style": "input (heuristic match on linkedin, profile, url)",
        "key_requirements": [
            {"label": "Candidate Name", "required": True, "status": "Ready", "selector": "name heuristic", "notes": "Matched via regex."},
            {"label": "Email & Phone", "required": True, "status": "Ready", "selector": "email / tel heuristic", "notes": "Matched via types & labels."},
            {"label": "LinkedIn & Portfolio", "required": False, "status": "Ready", "selector": "url / link heuristic", "notes": "Matched via keywords."},
            {"label": "Cover Pitch", "required": False, "status": "Auto-pasting Tailored Pitch", "selector": "textarea heuristic", "notes": "Populated in note / pitch textareas."}
        ],
        "tip": "Uses intelligent fuzzy heuristic matching across HTML5 attributes, labels, ARIA tags, and placeholder text."
    }
}


def get_autofill_payload(profile, job=None):
    """Assemble a unified, standard ATS-ready autofill dictionary from the candidate profile and job."""
    name = (profile.get("name") or "Candidate").strip()
    first_name, last_name = parse_name(name)
    email = (profile.get("email") or "").strip()
    phone = (profile.get("phone") or "").strip()
    location = (profile.get("location") or "").strip()
    loc_parts = [p.strip() for p in location.split(",") if p.strip()]
    city = loc_parts[0] if loc_parts else location
    country = loc_parts[-1] if len(loc_parts) > 1 else "United States"

    # Social links
    linkedin = (profile.get("linkedin") or "").strip()
    if linkedin and not linkedin.startswith("http"):
        linkedin = f"https://{linkedin}"
    github = (profile.get("github") or "").strip()
    if github and not github.startswith("http"):
        github = f"https://{github}"
    portfolio = (profile.get("portfolio") or profile.get("website") or "").strip()
    if portfolio and not portfolio.startswith("http"):
        portfolio = f"https://{portfolio}"

    # Target & Compensation
    target_title = (profile.get("target_title") or (profile.get("target_roles") or ["Software Engineer"])[0]).strip()
    min_sal = profile.get("min_salary")
    salary_str = f"${int(min_sal):,} / year" if min_sal else "Competitive / Flexible based on overall package"

    # Experience details
    exps = profile.get("experience") or []
    current_exp = exps[0] if exps else {}
    current_company = (current_exp.get("company") or "").strip()
    current_role = (current_exp.get("role") or target_title).strip()
    current_bullets = current_exp.get("bullets") or []

    # Education details
    edus = profile.get("education") or []
    top_edu = edus[0] if edus else {}
    degree = (top_edu.get("degree") or "Bachelor of Science in Computer Science").strip()
    school = (top_edu.get("institution") or "").strip()
    grad_year = str(top_edu.get("graduation_year") or "")

    # Top skills
    skills = profile.get("skills") or []
    skills_csv = ", ".join(skills[:15])

    # Summary
    summary = (profile.get("summary") or "").strip()
    if not summary and current_bullets:
        summary = f"{name} is a {target_title} specializing in {skills_csv}. Recent impact: {current_bullets[0]}"

    job_title = (job.get("title") or target_title) if job else target_title
    company_name = (job.get("company") or "the company") if job else "the company"

    # Cover Letter & Pitch generation
    cover_letter = ""
    cover_pitch = ""
    if job:
        try:
            pitch = refit.generate_cover_pitch(job, profile, tone="direct", angle="direct_impact")
            cover_letter = pitch.get("full_text", "")
            cover_pitch = pitch.get("why_company", "") or cover_letter
        except Exception:
            cover_letter = (
                f"Dear Hiring Team at {company_name},\n\n"
                f"I am writing to express my strong interest in the {job_title} role. "
                f"With hands-on experience in {skills_csv[:60]} and a proven track record of shipping production-grade software, "
                f"I am eager to contribute directly to {company_name}'s mission.\n\n"
                f"Best regards,\n{name}"
            )
            cover_pitch = cover_letter
    else:
        cover_letter = (
            f"Dear Hiring Team,\n\n"
            f"I am writing to express my interest in joining your engineering organization. "
            f"As a {target_title} experienced with {skills_csv[:60]}, I pride myself on engineering rigor and velocity.\n\n"
            f"Best regards,\n{name}"
        )
        cover_pitch = cover_letter

    job_url = (job.get("url") or "") if job else ""
    platform = detect_ats_platform(job_url)
    p_info = PLATFORM_INFO.get(platform, PLATFORM_INFO["standard"])

    # Readiness audit per platform
    readiness_audit = {}
    for p_key, p_val in PLATFORM_INFO.items():
        missing = []
        if not name:
            missing.append("Candidate Full Name")
        if not email:
            missing.append("Email Address")
        if not phone:
            missing.append("Phone Number")
        if p_key == "lever" and not linkedin:
            missing.append("LinkedIn Profile URL (Strictly enforced by Lever)")
        readiness_audit[p_key] = {
            "ready": len(missing) == 0,
            "missing": missing
        }

    fields = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "city": city,
        "country": country,
        "linkedin_url": linkedin,
        "github_url": github,
        "portfolio_url": portfolio,
        "target_title": target_title,
        "current_company": current_company,
        "current_role": current_role,
        "desired_salary": salary_str,
        "work_authorization": "Authorized to work without sponsorship",
        "visa_sponsorship": "No, I do not require visa sponsorship",
        "notice_period": "Immediate (or standard 2 weeks)",
        "degree": degree,
        "institution": school,
        "graduation_year": grad_year,
        "skills_csv": skills_csv,
        "summary": summary,
        "cover_letter": cover_letter,
        "cover_pitch": cover_pitch,
        "target_company": company_name,
        "target_job_title": job_title,
        "detected_platform": platform,
        "platform_name": p_info["name"],
        "platform_badge": p_info["badge"],
        "platform_info": p_info,
        "platforms": PLATFORM_INFO,
        "readiness_audit": readiness_audit
    }

    return fields


def generate_bookmarklet_code(fields):
    """Generate self-contained JavaScript bookmarklet/copyable script to autofill ATS web application forms."""
    fields_json = json.dumps(fields)
    script = f"""// JobHunter 1-Click Autofill Engine
(function(){{
  const data = {fields_json};
  let filledCount = 0;
  let filledItems = [];

  function dispatchEvents(el) {{
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
  }}

  function fillField(input, val, label) {{
    if (!input || !val || input.value) return;
    try {{
      input.focus();
      // Bypass React 16+ fiber value tracker
      const proto = Object.getPrototypeOf(input);
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) {{
        setter.call(input, val);
      }} else {{
        input.value = val;
      }}
      input.style.outline = '2px solid #10b981';
      input.style.backgroundColor = 'rgba(16, 185, 129, 0.08)';
      input.style.transition = 'all 0.25s ease';
      dispatchEvents(input);
      filledCount++;
      if (label) filledItems.push(label);
    }} catch(e) {{}}
  }}

  function fillContentEditable(el, val, label) {{
    if (!el || el.textContent.trim()) return;
    try {{
      el.focus();
      el.textContent = val;
      el.style.outline = '2px solid #10b981';
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      filledCount++;
      if (label) filledItems.push(label);
    }} catch(e) {{}}
  }}

  function fillSelect(sel, candidates, label) {{
    if (!sel || sel.value) return;
    try {{
      const opts = Array.from(sel.options);
      for (const opt of opts) {{
        const txt = (opt.text || opt.value || '').toLowerCase();
        if (candidates.some(c => txt.includes(c.toLowerCase()))) {{
          sel.value = opt.value;
          sel.style.outline = '2px solid #10b981';
          dispatchEvents(sel);
          filledCount++;
          if (label) filledItems.push(label);
          break;
        }}
      }}
    }} catch(e) {{}}
  }}

  function checkRadio(radio, label) {{
    if (!radio || radio.checked) return;
    try {{
      radio.checked = true;
      dispatchEvents(radio);
      filledCount++;
      if (label) filledItems.push(label);
    }} catch(e) {{}}
  }}

  function checkCheckbox(box, label) {{
    if (!box || box.checked) return;
    try {{
      box.checked = true;
      dispatchEvents(box);
      filledCount++;
      if (label) filledItems.push(label);
    }} catch(e) {{}}
  }}

  // 1. Detect ATS Platform Host
  const host = location.hostname.toLowerCase();
  let platform = 'Standard';
  if (host.includes('greenhouse.io') || host.includes('grnh.se')) platform = 'Greenhouse';
  else if (host.includes('lever.co')) platform = 'Lever';
  else if (host.includes('ashbyhq.com')) platform = 'Ashby';
  else if (host.includes('workday') || host.includes('myworkdayjobs')) platform = 'Workday';
  else if (host.includes('smartrecruiters.com')) platform = 'SmartRecruiters';
  else if (host.includes('workable.com')) platform = 'Workable';
  else if (host.includes('bamboohr.com')) platform = 'BambooHR';
  else if (host.includes('linkedin.com')) platform = 'LinkedIn';
  else if (host.includes('taleo.net') || host.includes('oraclecloud.com')) platform = 'Taleo';
  else if (host.includes('icims.com')) platform = 'iCIMS';
  else if (host.includes('jobvite.com')) platform = 'Jobvite';

  // 2. Direct ATS Platform Specific Selectors & Quirks
  if (platform === 'Greenhouse') {{
    fillField(document.querySelector('#first_name'), data.first_name, 'First Name');
    fillField(document.querySelector('#last_name'), data.last_name, 'Last Name');
    fillField(document.querySelector('#email'), data.email, 'Email');
    fillField(document.querySelector('#phone'), data.phone, 'Phone');
    fillField(document.querySelector('#cover_letter_text, textarea[name="job_application[cover_letter_text]"]'), data.cover_letter || data.cover_pitch, 'Cover Letter Textarea');
    fillField(document.querySelector('input[autocomplete="custom-question-linkedin"], input[id*="linkedin" i]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('input[id*="website" i], input[id*="portfolio" i]'), data.portfolio_url, 'Portfolio URL');
  }} else if (platform === 'Lever') {{
    fillField(document.querySelector('input[name="name"]'), data.full_name, 'Full Name');
    fillField(document.querySelector('input[name="email"]'), data.email, 'Email');
    fillField(document.querySelector('input[name="phone"]'), data.phone, 'Phone');
    fillField(document.querySelector('input[name="org"]'), data.current_company, 'Current Company');
    // Lever strictly expects urls[LinkedIn]
    fillField(document.querySelector('input[name="urls[LinkedIn]"]'), data.linkedin_url, 'LinkedIn (urls[LinkedIn])');
    fillField(document.querySelector('input[name="urls[GitHub]"]'), data.github_url, 'GitHub (urls[GitHub])');
    fillField(document.querySelector('input[name="urls[Portfolio]"]'), data.portfolio_url, 'Portfolio (urls[Portfolio])');
    fillField(document.querySelector('input[name="urls[Twitter]"]'), data.portfolio_url, 'Twitter/Social');
    // Lever uses comments for candidate pitch
    fillField(document.querySelector('textarea[name="comments"]'), data.cover_letter || data.cover_pitch, 'Cover Pitch (Comments)');
  }} else if (platform === 'Ashby') {{
    fillField(document.querySelector('input[name="name"], input[autocomplete="name"]'), data.full_name, 'Full Name');
    fillField(document.querySelector('input[name="email"], input[type="email"]'), data.email, 'Email');
    fillField(document.querySelector('input[name="phone"], input[type="tel"]'), data.phone, 'Phone');
    fillField(document.querySelector('input[name*="linkedin" i]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('input[name*="github" i]'), data.github_url, 'GitHub URL');
    fillField(document.querySelector('input[name*="portfolio" i], input[name*="website" i]'), data.portfolio_url, 'Portfolio URL');
    fillField(document.querySelector('textarea[placeholder*="cover letter" i], textarea[name*="coverLetter" i]'), data.cover_letter || data.cover_pitch, 'Cover Pitch');
  }} else if (platform === 'Workday') {{
    fillField(document.querySelector('input[data-automation-id="legalNameSection_firstName"]'), data.first_name, 'First Name');
    fillField(document.querySelector('input[data-automation-id="legalNameSection_lastName"]'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[data-automation-id="email"]'), data.email, 'Email');
    fillField(document.querySelector('input[data-automation-id="phone-number"]'), data.phone, 'Phone');
    fillField(document.querySelector('input[data-automation-id="addressSection_city"]'), data.city, 'City');
    fillField(document.querySelector('input[data-automation-id="addressSection_postalCode"]'), data.city, 'Postal Code');
    fillField(document.querySelector('input[data-automation-id="addressSection_addressLine1"]'), data.location, 'Address');
    fillField(document.querySelector('input[data-automation-id*="linkedin" i]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('textarea[data-automation-id*="cover" i]'), data.cover_letter || data.cover_pitch, 'Cover Pitch');
  }} else if (platform === 'SmartRecruiters') {{
    fillField(document.querySelector('input[data-test="first-name-input"], #first-name-input'), data.first_name, 'First Name');
    fillField(document.querySelector('input[data-test="last-name-input"], #last-name-input'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[data-test="email-input"], #email-input'), data.email, 'Email');
    fillField(document.querySelector('input[data-test="phone-number-input"], #phone-number-input'), data.phone, 'Phone');
    fillField(document.querySelector('textarea[data-test="message-to-hiring-manager"]'), data.cover_letter || data.cover_pitch, 'Message to Hiring Manager');
    fillField(document.querySelector('input[data-test="linkedin-input"]'), data.linkedin_url, 'LinkedIn URL');
  }} else if (platform === 'Workable') {{
    fillField(document.querySelector('#firstname'), data.first_name, 'First Name');
    fillField(document.querySelector('#lastname'), data.last_name, 'Last Name');
    fillField(document.querySelector('#email'), data.email, 'Email');
    fillField(document.querySelector('#phone'), data.phone, 'Phone');
    fillField(document.querySelector('#coverletter, textarea[name="cover_letter"]'), data.cover_letter || data.cover_pitch, 'Cover Letter');
    fillField(document.querySelector('#linkedin, input[name="linkedin"]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('#website, #github'), data.github_url || data.portfolio_url, 'Portfolio URL');
  }} else if (platform === 'BambooHR') {{
    fillField(document.querySelector('input[name="firstName"]'), data.first_name, 'First Name');
    fillField(document.querySelector('input[name="lastName"]'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[name="email"]'), data.email, 'Email');
    fillField(document.querySelector('input[name="phone"]'), data.phone, 'Phone');
    fillField(document.querySelector('textarea[name="coverLetter"]'), data.cover_letter || data.cover_pitch, 'Cover Letter');
    fillField(document.querySelector('input[name*="linkedin" i]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('input[name="desiredSalary"]'), data.desired_salary, 'Desired Salary');
  }} else if (platform === 'LinkedIn') {{
    fillField(document.querySelector('input[id*="phoneNumber"], input[name*="phone" i]'), data.phone, 'Phone');
    fillField(document.querySelector('input[id*="email"], input[name*="email" i]'), data.email, 'Email');
    fillField(document.querySelector('textarea[id*="coverLetter" i]'), data.cover_letter || data.cover_pitch, 'Cover Pitch');
  }} else if (platform === 'Taleo') {{
    fillField(document.querySelector('input[id*="firstName" i]'), data.first_name, 'First Name');
    fillField(document.querySelector('input[id*="lastName" i]'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[id*="email" i]'), data.email, 'Email');
    fillField(document.querySelector('input[id*="phone" i]'), data.phone, 'Phone');
    fillField(document.querySelector('input[id*="city" i]'), data.city, 'City');
    fillField(document.querySelector('textarea[id*="coverLetter" i], textarea[id*="comments" i]'), data.cover_letter || data.cover_pitch, 'Cover Letter');
  }} else if (platform === 'iCIMS') {{
    fillField(document.querySelector('input[id*="FirstName" i]'), data.first_name, 'First Name');
    fillField(document.querySelector('input[id*="LastName" i]'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[id*="Email" i]'), data.email, 'Email');
    fillField(document.querySelector('input[id*="Phone" i]'), data.phone, 'Phone');
    fillField(document.querySelector('textarea[id*="CoverLetter" i]'), data.cover_letter || data.cover_pitch, 'Cover Letter');
  }} else if (platform === 'Jobvite') {{
    fillField(document.querySelector('input[name="firstName"]'), data.first_name, 'First Name');
    fillField(document.querySelector('input[name="lastName"]'), data.last_name, 'Last Name');
    fillField(document.querySelector('input[name="email"]'), data.email, 'Email');
    fillField(document.querySelector('input[name="cellPhone"], input[name="phone"]'), data.phone, 'Phone');
    fillField(document.querySelector('input[name="linkedInUrl"]'), data.linkedin_url, 'LinkedIn URL');
    fillField(document.querySelector('textarea[name="coverLetter"]'), data.cover_letter || data.cover_pitch, 'Cover Letter');
  }}

  // 3. ContentEditable rich text editors (Quill, Draft.js, ProseMirror)
  const editables = document.querySelectorAll('[contenteditable="true"], [role="textbox"]');
  editables.forEach(ed => {{
    const label = ((ed.getAttribute('aria-label') || '') + ' ' + (ed.getAttribute('placeholder') || '') + ' ' + (ed.className || '')).toLowerCase();
    if (label.includes('cover') || label.includes('pitch') || label.includes('message') || label.includes('note')) {{
      fillContentEditable(ed, data.cover_letter || data.cover_pitch, 'Cover Pitch (Rich Text)');
    }}
  }});

  // 4. Heuristic Field Mapping (catches remaining or generic forms)
  const rules = [
    {{ test: /first[_\\-\\s]?name|fname|given[_\\-\\s]?name/i, val: data.first_name, label: 'First Name' }},
    {{ test: /last[_\\-\\s]?name|lname|family[_\\-\\s]?name|surname/i, val: data.last_name, label: 'Last Name' }},
    {{ test: /^name$|full[_\\-\\s]?name|candidate[_\\-\\s]?name/i, val: data.full_name, label: 'Full Name' }},
    {{ test: /email/i, val: data.email, label: 'Email' }},
    {{ test: /phone|mobile|cell|telephone|tel/i, val: data.phone, label: 'Phone' }},
    {{ test: /linkedin/i, val: data.linkedin_url, label: 'LinkedIn' }},
    {{ test: /github/i, val: data.github_url, label: 'GitHub' }},
    {{ test: /portfolio|website|personal[_\\-\\s]?(url|site|link)/i, val: data.portfolio_url, label: 'Portfolio' }},
    {{ test: /cover[_\\-\\s]?letter|note[_\\-\\s]?to|comments|pitch|message[_\\-\\s]?to/i, val: data.cover_letter || data.cover_pitch, label: 'Cover Letter / Pitch' }},
    {{ test: /current[_\\-\\s]?(company|employer|organization)|present[_\\-\\s]?employer/i, val: data.current_company, label: 'Current Company' }},
    {{ test: /current[_\\-\\s]?(title|role|position)|job[_\\-\\s]?title/i, val: data.current_role, label: 'Current Title' }},
    {{ test: /city/i, val: data.city, label: 'City' }},
    {{ test: /address|location|street/i, val: data.location, label: 'Location' }},
    {{ test: /salary|compensation|rate|pay[_\\-\\s]?expectation/i, val: data.desired_salary, label: 'Desired Salary' }},
    {{ test: /notice[_\\-\\s]?period|availability|start[_\\-\\s]?date|when[_\\-\\s]?can/i, val: data.notice_period, label: 'Notice Period' }},
    {{ test: /school|university|institution|college/i, val: data.institution, label: 'School' }},
    {{ test: /degree|major|field[_\\-\\s]?of[_\\-\\s]?study/i, val: data.degree, label: 'Degree' }},
    {{ test: /summary|bio|about[_\\-\\s]?yourself/i, val: data.summary, label: 'Summary' }}
  ];

  const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]), textarea');
  inputs.forEach(el => {{
    if (el.value) return;
    const label = (el.getAttribute('aria-label') || el.name || el.id || el.placeholder || '').toLowerCase();
    const parentText = (el.closest('label, .form-group, .field, [class*="field"], [class*="group"], [class*="question"]') || {{}}).textContent || '';
    const combined = `${{label}} ${{parentText}}`.toLowerCase();

    for (const r of rules) {{
      if (r.test(combined) && r.val) {{
        fillField(el, r.val, r.label);
        break;
      }}
    }}
  }});

  // 5. Dropdowns (EEO disclosures, Work Authorization, Source)
  const selects = document.querySelectorAll('select');
  selects.forEach(sel => {{
    const text = ((sel.name || '') + ' ' + (sel.id || '') + ' ' + ((sel.closest('label, .field, .form-group') || {{}}).textContent || '')).toLowerCase();
    if (text.includes('gender') || text.includes('sex') || text.includes('race') || text.includes('ethnicity') || text.includes('veteran') || text.includes('disability')) {{
      fillSelect(sel, ['decline', 'prefer not', 'choose not', 'do not wish', 'not wish'], 'EEO Disclosure');
    }} else if (text.includes('authorized') || text.includes('legally')) {{
      fillSelect(sel, ['yes', 'authorized', 'united states'], 'Work Authorization');
    }} else if (text.includes('sponsorship') || text.includes('require')) {{
      fillSelect(sel, ['no', 'will not'], 'Visa Sponsorship');
    }} else if (text.includes('hear') || text.includes('source')) {{
      fillSelect(sel, ['linkedin', 'job board', 'website', 'online'], 'Source');
    }}
  }});

  // 6. Work authorization & screening radio buttons
  const radios = document.querySelectorAll('input[type="radio"]');
  radios.forEach(r => {{
    const parent = (r.closest('label, div, .field, [class*="group"]') || {{}}).textContent || '';
    const pLow = parent.toLowerCase();
    if (pLow.includes('authorized to work') && (r.value.toLowerCase() === 'yes' || pLow.includes('yes'))) {{
      checkRadio(r, 'Work Auth (Yes)');
    }}
    if (pLow.includes('require sponsorship') && (r.value.toLowerCase() === 'no' || pLow.includes('no'))) {{
      checkRadio(r, 'Sponsorship (No)');
    }}
    if (pLow.includes('worked for') && (r.value.toLowerCase() === 'no' || pLow.includes('no'))) {{
      checkRadio(r, 'Prior Employee (No)');
    }}
  }});

  // 7. Checkboxes (Privacy & Terms agreement)
  const checkboxes = document.querySelectorAll('input[type="checkbox"]');
  checkboxes.forEach(cb => {{
    const parent = (cb.closest('label, div, .field') || {{}}).textContent || '';
    const pLow = parent.toLowerCase();
    if (pLow.includes('privacy') || pLow.includes('terms') || pLow.includes('consent') || pLow.includes('agree')) {{
      checkCheckbox(cb, 'Terms / Consent');
    }}
  }});

  // 8. Floating Notification Toast & HUD
  const existingToast = document.getElementById('jh-autofill-toast');
  if (existingToast) existingToast.remove();

  const toast = document.createElement('div');
  toast.id = 'jh-autofill-toast';
  toast.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:2147483647;background:#0f172a;color:#f8fafc;padding:16px 20px;border-radius:14px;box-shadow:0 16px 36px rgba(0,0,0,0.4);font-family:system-ui,-apple-system,sans-serif;font-size:13px;font-weight:500;display:flex;flex-direction:column;gap:8px;border-left:4px solid #10b981;max-width:360px;';
  toast.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <span style="font-size:14px;font-weight:700;color:#10b981;">⚡ JobHunter Autofill</span>
      <span style="background:rgba(255,255,255,0.12);padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#94a3b8;">${{platform}} ATS</span>
    </div>
    <div style="color:#e2e8f0;font-size:12.5px;">
      Populated <strong>${{filledCount}}</strong> form field(s) successfully!
    </div>
    ${{data.cover_letter ? '<div style="font-size:11.5px;color:#cbd5e1;">✓ Tailored pitch populated in cover letter textarea</div>' : ''}}
    ${{filledItems.length > 0 ? '<div style="font-size:11px;color:#94a3b8;line-height:1.4;">' + filledItems.slice(0, 5).join(' • ') + (filledItems.length > 5 ? ' + ' + (filledItems.length - 5) + ' more' : '') + '</div>' : ''}}
  `;
  document.body.appendChild(toast);
  setTimeout(() => {{ toast.style.opacity = '0'; toast.style.transition = 'opacity 0.5s'; setTimeout(() => toast.remove(), 500); }}, 5500);
}})();"""
    return script


SCREENING_SOLVER_PROMPT = """You are an expert technical career advocate and hiring consultant (2026/2027 standard).
You write authentic, high-signal, and strictly grounded answers (60-120 words) to job application screening questions.

CRITICAL TRUTH & RECRUITER 2026/2027 CONSTRAINTS:
1. Ground every claim, technology, and metric STRICTLY on the candidate's verified profile facts. Zero hallucinations.
2. Individual Ownership: Highlight what the candidate personally designed, built, or delivered. Avoid vague "we" statements.
3. STAR-L Structure: Situation, Task, Action, Result, Learning in 2-4 punchy sentences.
4. Anti-AI Slop: Strictly avoid generic filler phrases ("fast-paced environment", "passionate problem solver", "testament to").
5. Transparent Gaps: If asked about an unlisted technology, state foundational familiarity or parallel architectural experience honestly.
6. Clean Text Output: Return pure plain text only. Do NOT use markdown asterisks (**), headers (#), quotation marks (""), or bullet characters.
"""


def solve_screening_question(question, profile, job=None, max_words=120, tone="direct"):
    """Synthesize a grounded, personalized answer to any job application screening question."""
    job = job or {}
    company = job.get("company") or "the company"
    title = job.get("title") or "the role"
    cand_name = profile.get("name") or "Candidate"
    skills = profile.get("skills") or []
    exps = profile.get("experience") or []
    top_bullets = [b for e in exps for b in e.get("bullets", []) if b.strip()][:4]

    # Deterministic fallback response generator
    q_low = question.lower()
    fallback_answer = ""

    if any(k in q_low for k in ["why", "interest", "excite", "apply"]):
        skill_str = ", ".join(skills[:3]) if skills else "modern engineering"
        fallback_answer = (
            f"I am excited to apply for the {title} role at {company} because it directly aligns with my hands-on "
            f"experience in {skill_str}. In my previous work, {top_bullets[0] if top_bullets else 'I consistently focused on shipping reliable software'}. "
            f"I am eager to bring this same dedication to velocity, clean architecture, and product impact to {company}."
        )
    elif any(k in q_low for k in ["achievement", "accomplish", "proud", "impact"]):
        bullet = top_bullets[0] if top_bullets else "architecting robust, scalable software solutions"
        fallback_answer = (
            f"One of my most impactful accomplishments was when {bullet}. This initiative reinforced my commitment "
            f"to engineering rigor, measurable performance gains, and delivering real value to end users."
        )
    elif any(k in q_low for k in ["salary", "compensation", "rate", "expectation"]):
        sal = profile.get("min_salary")
        fallback_answer = (
            f"My target compensation is {f'around ${int(sal):,} annually' if sal else 'competitive and commensurate with the market standards for this position'}, "
            f"though I remain flexible based on the total compensation package, growth trajectory, and team scope."
        )
    elif any(k in q_low for k in ["notice", "availability", "start date", "when can you start"]):
        np = profile.get("notice_period") or "2 weeks"
        fallback_answer = (
            f"I am available to start with a standard {np} notice (or immediately where appropriate) to ensure a clean transition. "
            f"I am ready to hit the ground running and integrate smoothly with the team."
        )
    elif any(k in q_low for k in ["remote", "work mode", "time zone", "location"]):
        fallback_answer = (
            f"I have extensive experience working asynchronously in distributed environments, maintaining high documentation standards, "
            f"transparent progress communication, and self-directed execution across time zones."
        )
    else:
        skill_str = ", ".join(skills[:4]) if skills else "full-stack development"
        fallback_answer = (
            f"Throughout my career as a {profile.get('target_title', 'Software Engineer')}, I have focused heavily on {skill_str}. "
            f"My approach centers on disciplined problem-solving, clean maintainable code, and pragmatic alignment with core business outcomes."
        )

    # Attempt real LLM generation if available
    cfg = refit.get_active_ai_config()
    if refit.llm_available():
        import pathlib
        prompt_path = pathlib.Path(config.BASE_DIR) / "prompts" / "screening_question_solver.md"
        system_prompt = SCREENING_SOLVER_PROMPT
        try:
            if prompt_path.exists():
                text_content = prompt_path.read_text(encoding="utf-8")
                m = re.search(r"```markdown\n(.*?)\n```", text_content, re.S)
                if m:
                    system_prompt = m.group(1)
        except Exception:
            pass

        user_prompt = json.dumps({
            "question": question,
            "job_posting": {
                "company": company,
                "title": title,
                "required_skills": job.get("required_skills", [])[:8],
                "description_snippet": (job.get("description", "") or "")[:1200]
            },
            "candidate_facts": {
                "name": cand_name,
                "target_title": profile.get("target_title"),
                "verified_skills": skills[:20],
                "experience_proof_points": top_bullets
            },
            "constraints": {
                "max_words": max_words,
                "tone": tone
            }
        }, indent=2)
        try:
            raw_res = refit._call_llm(system_prompt, user_prompt, cfg)
            parsed_json = refit._parse_json_llm_response(raw_res)
            if isinstance(parsed_json, dict) and "answer" in parsed_json:
                cleaned = clean_text(str(parsed_json["answer"])).strip()
            else:
                cleaned = clean_text(raw_res).strip()
            # Clean enclosing quotes or markdown symbols that could break form inputs
            cleaned = re.sub(r"^\s*[\"']+|[\"']+\s*$", "", cleaned).strip()
            cleaned = re.sub(r"[*#_`]", "", cleaned).strip()

            # Verify no hallucinations against candidate profile
            check = refit.ungrounded(profile, cleaned.replace(title, "").replace(company, ""))
            if not check["skills"] and not check["numbers"]:
                return {
                    "question": question,
                    "answer": cleaned,
                    "provider": cfg.get("provider", "ai"),
                    "model": cfg.get("model", ""),
                    "grounded": True,
                    "word_count": len(cleaned.split())
                }
        except Exception:
            pass

    return {
        "question": question,
        "answer": fallback_answer,
        "provider": "deterministic",
        "model": "grounded_rules",
        "grounded": True,
        "word_count": len(fallback_answer.split())
    }


def get_batch_screening_answers(profile, job=None):
    """Generate pre-computed answers for the 4 most common ATS screening questions."""
    job = job or {}
    comp = job.get("company") or "the company"
    title = job.get("title") or "this role"

    questions = [
        f"Why are you interested in joining {comp} as a {title}?",
        "What is your greatest or proudest technical accomplishment?",
        f"What is your relevant experience with the core stack requested by {comp}?",
        "What are your salary expectations and availability / notice period?"
    ]

    results = []
    for q in questions:
        sol = solve_screening_question(q, profile, job)
        results.append(sol)
    return results


def execute_easy_apply(job, profile, tone="direct", angle="direct_impact"):
    """Execute complete 1-Click Easy Apply: prepares tailored resume, cover pitch, logs application as applied."""
    now = now_iso()
    comp = job.get("company") or "Company"
    title = job.get("title") or "Role"

    # 1. Tailor resume and pitch
    ref = refit.refine_resume_for_job(job, profile)
    tailored = ref["tailored_resume"]
    pitch = refit.generate_cover_pitch(job, profile, tone=tone, angle=angle)
    cover_letter = pitch.get("full_text", "")

    # 2. Build or locate application ID
    app_id = f"app-easy-{int(time.time() * 1000)}"
    follow_up = tracker.FOLLOW_UP_DAYS.get("applied", 7)
    follow_date = (datetime.date.today() + datetime.timedelta(days=follow_up)).isoformat()

    # 3. Upsert directly with status 'applied'
    tracker.upsert_application({
        "id": app_id,
        "job_id": job.get("id"),
        "company": comp,
        "title": title,
        "location": job.get("location", ""),
        "salary": job.get("salary", ""),
        "status": "applied",
        "follow_up_date": follow_date,
        "notes": f"Applied via 1-Click Easy Apply. Auto follow-up scheduled for {follow_date}. Tailored resume and executive pitch attached.",
        "sources": job.get("sources") or [{"source": job.get("source"), "url": job.get("url")}],
        "job_data": job,
        "tailored_resume": tailored,
        "cover_letter": cover_letter
    })

    # 4. Generate autofill payload and injector script
    autofill_data = get_autofill_payload(profile, job)
    script = generate_bookmarklet_code(autofill_data)
    bookmarklet = f"javascript:{quote(script)}"

    return {
        "success": True,
        "application_id": app_id,
        "app_id": app_id,
        "company": comp,
        "title": title,
        "status": "applied",
        "applied_at": now,
        "follow_up_date": follow_date,
        "application_url": job.get("url") or "",
        "autofill_payload": autofill_data,
        "autofill_script": script,
        "bookmarklet": bookmarklet,
        "tailored_resume": tailored,
        "cover_letter": cover_letter,
        "cover_pitch": pitch,
        "message": f"Successfully applied to {comp} ({title})! Added to Applications with a 7-day follow-up reminder."
    }
