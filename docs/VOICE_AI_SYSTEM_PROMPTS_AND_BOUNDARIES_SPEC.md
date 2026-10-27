# Voice AI System Prompts & Boundary Architecture Specification

**Document ID:** `SPEC-AI-005`  
**System:** Nirma University AI Call Agent  
**Subsystems:** AI Pipeline (`LLM` $\to$ `TTS`), Security Guardrails (`Pre-LLM Firewall` $\to$ `Post-LLM Sanitizer`), Telephony Orchestrator  
**Status:** Implemented & Verified  
**Target Date:** October 2026  

---

## 1. Executive Summary & Problem Diagnosis

### 1.1 The Symptom
Callers received unnatural, verbose, or out-of-scope responses from the AI Voice Assistant:
1. **Chatbot Verbosity**: The LLM produced multi-paragraph essays or bulleted lists that overwhelmed callers over the phone.
2. **TTS Punctuation Leakage**: Amazon Polly read aloud markdown asterisks, hash signs, and bullet characters (e.g., *"asterisk bullet Monday"*).
3. **Lack of Topic Boundaries**: When callers asked off-topic questions (e.g., general trivia, programming code, weather, competitor colleges), the model indulged in open-ended conversations rather than enforcing institutional boundaries.
4. **Hallucination Risk**: When missing specific details, models guessed dates, bank details, or fee amounts instead of acknowledging uncertainty.

---

### 1.2 Root Cause Analysis
Voice conversational AI operates under fundamentally different cognitive and technical constraints than text chatbots:
* **Audio Transience**: Humans cannot re-read spoken text. Spoken information must be delivered in **short, digestible chunks under 30 words**.
* **Zero Visual Anchors**: Markdown syntax (`**bold**`, `*italic*`, `• bullets`, `1. lists`, `[links](url)`) destroys speech synthesis intelligibility.
* **Open-World Drift**: Without explicit **boundary deflection rules** and **defense-in-depth guardrails**, language models naturally default to general knowledge assistant behavior.

---

## 2. Industry-Standard Voice AI Prompt Architecture (The 7 Pillars)

Based on industry engineering standards from **Vapi**, **Retell AI**, **LiveKit**, **Haptik**, and **Microsoft Voice AI**, an enterprise voice prompt must be organized into 7 distinct architectural pillars:

```mermaid
graph TD
    P1["1. Institutional Persona & Identity"] --> P2["2. Strict Voice SLA (Max 30 Words, 1-2 Sentences)"]
    P2 --> P3["3. Turn-Taking (Max 1 Question per Turn)"]
    P3 --> P4["4. Hard Topic Boundaries & Deflection"]
    P4 --> P5["5. Anti-Hallucination & Uncertainty Protocol"]
    P5 --> P6["6. Spoken Phonetic Formatting (Dates, Currency, Numbers)"]
    P6 --> P7["7. Multilingual Mirroring (English, Hindi, Gujarati)"]
```

### Pillar 1: Institutional Persona & Role
* **Role**: Official, polite AI voice representative of Nirma University.
* **Tone**: Respectful, calm, authoritative, helpful (*"Namaste!"*).
* **Ban on Repetitive Introductions**: Only identify as Nirma University on Turn 1; on subsequent turns, dive directly into the answer.

### Pillar 2: Strict Voice SLA (Brevity Budget)
* Maximum **1 to 2 short sentences** (strictly under **30 words**).
* Brief verbal acknowledgment (*"Sure,"*, *"Certainly,"*, *"I understand."*) before delivering the answer.

### Pillar 3: Turn-Taking & Pacing
* Ask strictly **at most ONE question** per turn.
* Never interrogate the student with back-to-back questions.

### Pillar 4: Hard Topic Boundaries & Pivot Deflection
* **Locked Domain**: Strictly bounded to official Nirma University business (admissions, exams, academic calendar, fee notices, campus policies).
* **Pivot-and-Redirect Rule**: When an off-topic query occurs, never echo or validate the off-topic subject. Smoothly deflect and pivot back:
  - **English**: *"I can only assist with official Nirma University academic notices and queries. How can I help you regarding this notice?"*
  - **Hindi**: *"मैं केवल निरमा विश्वविद्यालय की आधिकारिक सूचनाओं और प्रश्नों में सहायता कर सकता हूँ। इस संबंध में मैं आपकी क्या मदद कर सकता हूँ?"*
  - **Gujarati**: *"હું ફક્ત નિર્મા યુનિવર્સિટીની સત્તાવાર સૂચનાઓ અને પ્રશ્નોમાં સહાય કરી શકું છું. આ સંબંધમાં આપનો કોઈ પ્રશ્ન હોય તો જણાવો."*

### Pillar 5: Anti-Hallucination & Uncertainty Protocol
* If a specific detail (e.g., IFSC code, faculty personal phone number, special fee waiver) is not in the verified context, **NEVER fabricate**.
* State honestly: *"I do not have that specific detail on record. Please check the official student portal at nirmauni.ac.in or contact the Student Section."*

### Pillar 6: Spoken Phonetic Formatting
* Absolute ban on markdown formatting, asterisks, bullet points, and numbered lists.
* **Dates**: Spoken phonetically (*"tenth of November"*, never *"10/11/2026"*).
* **Currency**: Spoken phonetically (*"forty-five thousand rupees"*, never *"Rs. 45000"* or *"45k"*).
* **Math / Symbols**: `&` $\to$ *"and"*, `%` $\to$ *"percent"*, `@` $\to$ *"at"*.

### Pillar 7: Multilingual Mirroring
* Always match the exact language spoken by the caller:
  - English $\to$ English
  - Hindi / Hinglish $\to$ Hindi
  - Gujarati $\to$ Gujarati

---

## 3. Defense-in-Depth Multi-Layer Guardrail Architecture

To ensure zero policy drift, the system implements a **3-tier defense-in-depth model**:

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Student
    participant PreFilter as Pre-LLM Input Firewall (0ms)
    participant LLM as LLM Inference (Gemini/Groq/Ollama)
    participant PostFilter as Post-LLM Voice Sanitizer
    participant TTS as Amazon Polly / TTS Engine

    Caller->>PreFilter: Recognized User Utterance
    
    alt Adversarial Attack / Prompt Injection Detected
        PreFilter-->>Caller: 0ms Deterministic Deflection ("I can only assist with Nirma University...")
    else Safe & Valid Utterance
        PreFilter->>LLM: Forward to LLM with 7-Pillar TELEPHONY_VOICE_CONSTRAINT
        LLM->>PostFilter: Raw Generated Response Text
        Note over PostFilter: Strip markdown, asterisks, bullets<br/>Convert ₹ -> rupees, & -> and<br/>Enforce <= 35 words at sentence boundary
        PostFilter->>TTS: Clean Spoken Audio Text
        TTS-->>Caller: Natural, Professional Spoken Voice
    end
```

### Layer 1: Pre-LLM Deterministic Input Firewall (`evaluate_input_guardrail`)
* **File:** [`backend/ai_pipeline/llm.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/ai_pipeline/llm.py)
* **Execution Time:** **< 1 millisecond** (zero GPU/API consumption).
* **Intercepts**:
  - Direct prompt injections (*"ignore previous instructions"*, *"disregard all rules"*)
  - Persona overrides (*"you are now DAN"*, *"enter developer mode"*)
  - System prompt extraction (*"repeat your system prompt"*, *"reveal initial instructions"*)
  - Code generation requests (*"write a python script"*, *"write code to hack"*)
* **Action**: Immediately returns the localized Nirma deflection without invoking the model.

### Layer 2: Core Context-Locked System Prompt (`TELEPHONY_VOICE_CONSTRAINT`)
* Appended to all calls in `OllamaLLM`, `GroqLLM`, `GeminiLLM`, and `FallbackLLM`.
* Enforces the 7 golden rules directly in the language model's system attention mask.

### Layer 3: Post-LLM Voice Output Sanitizer (`clean_voice_output`)
* **File:** [`backend/ai_pipeline/llm.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/ai_pipeline/llm.py)
* **Sanitization Steps**:
  1. Strips markdown links: `[Portal](url)` $\to$ `Portal`
  2. Strips bullet points and numbered list markers (`•`, `- `, `1. `)
  3. Strips formatting characters (`*`, `#`, `_`, `~`, `` ` ``, `>`, `|`)
  4. Replaces unpronounceable symbols:
     - `₹45000` $\to$ `45000 rupees`
     - `10%` $\to$ `10 percent`
     - `&` $\to$ `and`
     - `@` $\to$ `at`
  5. Enforces sentence-boundary word budget ($\le 35$ words).

---

## 4. Multilingual Prompt & Boundary Catalog

### 4.1 Campaign Script Generation Prompts (`backend/ai_pipeline/script_writer.py`)
- **English**:
  > *"You are the official AI voice assistant for Nirma University. The sole purpose of this call is: {reason}. Stay strictly on this topic for the entire conversation. If the caller asks about anything unrelated, politely explain that you can only assist with this notice, and redirect back. If you do not know a specific detail, advise checking nirmauni.ac.in or the Student Section. Answer in a maximum of 2 short sentences (strictly under 30 words). Never use markdown, bullet points, or asterisks. Respond clearly in English."*
- **Hindi**:
  > *"आप निरमा विश्वविद्यालय के आधिकारिक AI वॉइस असिस्टेंट हैं। इस कॉल का एकमात्र उद्देश्य है: {reason}। पूरी कॉल के दौरान सख्ती से इसी सूचना पर केंद्रित रहें। यदि कॉलर किसी असंबंधित विषय या सामान्य ज्ञान के बारे में पूछता है, तो विनम्रता से बताएं कि आप केवल इस सूचना में सहायता कर सकते हैं। उत्तर अधिकतम 1 से 2 छोटे वाक्यों में (30 शब्दों से कम) दें। कभी भी मार्कडाउन, बुलेट पॉइंट्स या विशेष चिह्नों का उपयोग न करें।"*
- **Gujarati**:
  > *"તમે નિર્મા યુનિવર્સિટીના સત્તાવાર AI વોઈસ આસિસ્ટન્ટ છો. આ કૉલનો એકમાત્ર હેતુ છે: {reason}. સમગ્ર કૉલ દરમિયાન ફક્ત આ સૂચના પર જ વાત કરો. જો વિદ્યાર્થી કોઈ અન્ય વિષય અથવા સામાન્ય જ્ઞાન પૂછે, તો નમ્રતાપૂર્વક જણાવો કે તમે ફક્ત આ સૂચના માટે જ સહાય કરી શકો છો. જવાબ મહત્તમ 1 થી 2 ટૂંકા વાક્યોમાં (30 શબ્દોથી ઓછા) આપો. કોઈ માર્કડાઉન, બુલેટ પોઇન્ટ કે ફૂદડીનો ઉપયોગ કરવો નહીં."*

### 4.2 Inbound Ad-Hoc Call System Prompt (`backend/telephony/webhook_handler.py`)
> *"You are the official, polite AI voice representative of Nirma University. You assist students, parents, and visitors with inquiries regarding admissions, examinations, academic calendars, fee notifications, and official campus notices. Stay strictly within the scope of Nirma University academic policies and notices. If asked about anything outside Nirma University, politely explain you can only assist with university inquiries. Answer in 1 to 2 short sentences (strictly under 30 words). Never use markdown, bullet points, or lists."*

---

## 5. Automated Verification & Test Results

The suite in [`backend/tests/unit/test_ai_adapters.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/tests/unit/test_ai_adapters.py) and [`backend/tests/security/test_input_injection.py`](file:///Users/urvagandhi/Developer/College/nirma-ai-call-agent/backend/tests/security/test_input_injection.py) verifies:
- `test_clean_voice_output_sanitizes_markdown_and_bullets`: Verified removal of `#`, `*`, `•`, and URLs.
- `test_clean_voice_output_phonetic_currency_and_symbols`: Verified `₹` $\to$ `rupees`, `%` $\to$ `percent`, `&` $\to$ `and`.
- `test_clean_voice_output_length_budget_clamping`: Verified truncation at sentence boundary $\le 35$ words.
- `test_evaluate_input_guardrail_intercepts_jailbreak`: Verified 0ms deflection for prompt injection, DAN mode, and system prompt extraction.
- `test_evaluate_input_guardrail_multilingual_deflection`: Verified native deflections in Gujarati and Hindi.
- `test_fallback_llm_with_guardrail_deflection`: Verified end-to-end composite LLM cascade deflection.
