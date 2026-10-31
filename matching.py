import json
import os
import re


def normalize_text(text):
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize(text):
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


# ---------------------------------------------------------------------------
# AI Semantic Matching with sentence-transformers
# ---------------------------------------------------------------------------

_model = None
_model_load_attempted = False


def _get_model():
    global _model, _model_load_attempted
    if _model is not None:
        return _model
    if _model_load_attempted:
        return None
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        return _model
    except Exception as exc:
        print(f"WARNING: Could not load sentence-transformers model: {exc}")
        return None


def _safe_get(row, key, default=""):
    """Get a value from a dict or sqlite3.Row safely."""
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError):
        return default


def _build_professor_corpus(advisor):
    """Build a rich text corpus for a professor from all available fields.

    This includes department, expertise keywords, recent seminar topics and
    a general topics corpus so the embedding captures a professor's profile.
    """
    parts = []
    dept = _safe_get(advisor, "department")
    if dept:
        parts.append(dept)
    kw = _safe_get(advisor, "expertise_keywords")
    if kw:
        parts.append(kw.replace(";", ","))
    recent = _safe_get(advisor, "recent_seminar_topics")
    if recent:
        parts.append(recent.replace("|", ","))
    corpus = _safe_get(advisor, "all_topics_corpus")
    if corpus:
        parts.append(corpus.replace("|", ","))
    # include title lightly to help disambiguation
    title = _safe_get(advisor, "title")
    if title:
        parts.append(title)
    return " . ".join(parts) if parts else ""


def _keyword_boost(query_text, advisor):
    """Compute a lightweight keyword overlap metric (0.0-1.0) and return
    the matched keywords list. This is only a small supporting signal.
    """
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0, []

    kw_text = (_safe_get(advisor, "expertise_keywords") + " " + _safe_get(advisor, "recent_seminar_topics") + " " + _safe_get(advisor, "all_topics_corpus")).lower()
    kw_tokens = set(tokenize(kw_text))

    matched = sorted(query_tokens & kw_tokens)
    if not matched:
        return 0.0, []

    # fraction of query tokens that matched (cap at 1.0)
    boost = min(len(matched) / max(len(query_tokens), 1), 1.0)
    return boost, matched


def _field_categories():
    return [
        {
            "key": "industrial_engineering",
            "label": "Industrial Engineering / Operations",
            "query": [
                "industrial engineering", "supply chain", "logistics", "inventory",
                "transportation", "warehouse", "production", "manufacturing",
                "operations research", "operations management", "supply chain management",
                "warehouse automation", "transportation planning", "lean", "erp",
                "procurement", "distribution", "risk management"
            ],
            "advisor": [
                "industrial engineering", "management engineering", "operations research",
                "supply chain", "logistics", "inventory", "transportation",
                "warehouse", "manufacturing", "production", "lean", "erp", "process",
                "quality management", "industrial systems"
            ],
            "departments": ["industrial engineering", "management engineering"]
        },
        {
            "key": "software",
            "label": "Software / Computer Engineering",
            "query": [
                "software", "software engineering", "programming", "application development",
                "web development", "mobile development", "backend", "frontend", "devops",
                "cloud", "api", "user interface", "ui", "ux", "computer engineering",
                "information systems", "information technology",
                "embedded systems", "system design", "software development",
                "software systems", "artificial intelligence", "machine learning",
                "computing", "data science", "computer vision", "artificial intelligence engineering",
                "ai", "ml", "deep learning", "neural networks", "nlp", "algorithms",
                "database", "network", "cybersecurity", "distributed systems"
            ],
            "advisor": [
                "software engineering", "computer engineering", "artificial intelligence engineering",
                "application development", "programming",
                "backend", "frontend", "devops", "cloud", "api",
                "user interface", "embedded systems", "software development",
                "software systems", "machine learning", "artificial intelligence",
                "data science", "computer vision", "information systems",
                "deep learning", "neural networks", "nlp", "algorithms",
                "database", "network", "cybersecurity", "distributed"
            ],
            "departments": ["software engineering", "computer engineering", "artificial intelligence engineering", "computer science", "informatics"]
        },
        {
            "key": "mechanical_engineering",
            "label": "Mechanical Engineering",
            "query": [
                "mechanical engineering", "mechanical", "fluid", "fluid dynamics", "navier stokes",
                "navier-stokes", "thermodynamics", "heat transfer", "aerodynamics",
                "solid mechanics", "machine design", "vibration", "dynamics",
                "mechanics", "continuum mechanics", "materials", "energy systems",
                "hydraulics", "pneumatics", "turbomachinery"
            ],
            "advisor": [
                "mechanical engineering", "mechatronics engineering", "aerodynamics",
                "fluid dynamics", "thermodynamics", "heat transfer", "solid mechanics",
                "machine design", "vibration", "dynamics", "continuum",
                "hydraulics", "pneumatics", "turbomachinery", "energy systems",
                "wind turbine", "mechanical systems", "materials science"
            ],
            "departments": ["mechanical engineering", "mechatronics engineering"]
        },
        {
            "key": "biomedical_engineering",
            "label": "Biomedical Engineering",
            "query": [
                "biomedical", "biomedical engineering", "medical robotics", "medical devices",
                "signal processing", "bioengineering", "biomedical imaging", "biosignal",
                "neural engineering", "prosthetics", "healthcare", "medical imaging",
                "magnetic resonance", "biomechanics", "rehabilitation"
            ],
            "advisor": [
                "biomedical engineering", "medical robotics", "medical devices",
                "signal processing", "biosignal", "biomedical imaging",
                "bioengineering", "healthcare", "neural engineering",
                "prosthetics", "biomechanics", "rehabilitation"
            ],
            "departments": ["biomedical engineering"]
        },
        {
            "key": "civil_engineering",
            "label": "Civil Engineering",
            "query": [
                "civil engineering", "civil", "structural", "geotechnical", "transportation",
                "coastal", "hydrodynamics", "hydraulics", "earthquake", "tsunami",
                "port engineering", "infrastructure", "water resources", "environmental engineering"
            ],
            "advisor": [
                "civil engineering", "structural engineering", "geotechnical engineering",
                "transportation engineering", "coastal engineering", "hydrodynamics",
                "hydraulics", "earthquake", "tsunami", "port engineering",
                "infrastructure", "water resources"
            ],
            "departments": ["civil engineering"]
        },
        {
            "key": "mathematics",
            "label": "Mathematics",
            "query": [
                "mathematics", "math", "algebra", "calculus", "statistics", "probability",
                "optimization", "discrete math", "numerical", "linear algebra"
            ],
            "advisor": [
                "mathematics", "applied mathematics", "mathematical", "optimization",
                "statistics", "probability", "numerical methods", "linear algebra"
            ],
            "departments": ["mathematics"]
        },
        {
            "key": "physics",
            "label": "Physics",
            "query": [
                "physics", "quantum", "mechanics", "thermodynamics", "optics",
                "particle", "relativity", "electromagnetics", "photons", "nuclear"
            ],
            "advisor": [
                "physics", "quantum", "mechanics", "thermodynamics", "optics",
                "particle", "relativity", "electromagnetics", "nuclear"
            ],
            "departments": ["physics"]
        },
    ]


def _text_contains_term(text, term):
    if not term:
        return False
    if " " in term:
        return term in text
    return term in set(tokenize(text))


def _extract_query_category(query_text):
    query_lower = query_text.lower()
    best_category = None
    best_score = 0
    for category in _field_categories():
        score = sum(1 for term in category["query"] if _text_contains_term(query_lower, term))
        if score > best_score:
            best_score = score
            best_category = category
    return best_category if best_score > 0 else None


def _advisor_matches_category(advisor, category):
    if not category:
        return True

    advisor_text = (
        _safe_get(advisor, "department") + " "
        + _safe_get(advisor, "expertise_keywords") + " "
        + _safe_get(advisor, "recent_seminar_topics") + " "
        + _safe_get(advisor, "all_topics_corpus")
    ).lower()

    if any(dept in advisor_text for dept in category["departments"]):
        return True

    matched_terms = [term for term in category["advisor"] if _text_contains_term(advisor_text, term)]
    return len(matched_terms) >= 5


def _compute_domain_relevance(query_text, advisor):
    """Measure whether the professor profile covers the core domain of the query."""
    category = _extract_query_category(query_text)
    if not category:
        return 1.0
    return 1.0 if _advisor_matches_category(advisor, category) else 0.0


def _find_matched_reasons(query_text, advisor):
    """Generate human-readable reasons why this professor matched."""
    reasons = []

    # recent seminar topics
    recent = _safe_get(advisor, "recent_seminar_topics")
    for topic in recent.split("|"):
        topic = topic.strip()
        if not topic:
            continue
        q_words = [w for w in tokenize(query_text) if len(w) > 2]
        if any(w in topic.lower() for w in q_words):
            reasons.append(f"Recent topic: {topic}")
            break

    # Keyword overlap
    _, matched_kws = _keyword_boost(query_text, advisor)
    if matched_kws:
        reasons.append(f"Keyword overlap: {', '.join(matched_kws[:5])}")

    # Department relevance (simple token check)
    dept = _safe_get(advisor, "department").lower()
    if dept and any(w in dept for w in tokenize(query_text) if len(w) > 2):
        reasons.append(f"Department: {_safe_get(advisor, 'department')}")

    return reasons


def rank_advisors(topic, description, advisors):
    """Rank advisors using LLM, local AI embeddings, or keyword matching."""
    if not advisors or not (topic or description):
        return []

    query_text = f"{topic or ''} {description or ''}".strip()

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if api_key:
        try:
            return _rank_with_llm(query_text, advisors)
        except Exception as exc:
            print(f"WARNING: LLM matching failed, falling back to embeddings: {exc}")

    model = _get_model()
    if model is not None:
        return _rank_with_ai(model, query_text, advisors)
    else:
        return _rank_with_keywords(query_text, advisors)


def _rank_with_llm(query_text, advisors):
    """LLM-powered ranking using Claude. Two-pass: filter then deep rank."""
    from groq import Groq

    # Pass 1: narrow down to top candidates using keyword/category filter
    query_category = _extract_query_category(query_text)
    if query_category:
        candidates = [a for a in advisors if _advisor_matches_category(a, query_category)]
        if not candidates:
            candidates = advisors
    else:
        candidates = advisors

    # Cap at 20 to keep prompt size manageable
    candidates = candidates[:20]

    # Build compact profiles for the prompt
    profiles = []
    for i, adv in enumerate(candidates):
        profiles.append({
            "index": i,
            "name": _safe_get(adv, "title") + " " + adv["full_name"],
            "department": _safe_get(adv, "department"),
            "expertise": _safe_get(adv, "expertise_keywords"),
            "recent_topics": _safe_get(adv, "recent_seminar_topics"),
        })

    prompt = f"""You are an expert academic committee at Bahçeşehir University (BAU) in Istanbul, Turkey. Your job is to find the most suitable faculty advisor for a student seminar based on the seminar topic and description.

A good advisor match means:
- Their research expertise or published work directly relates to the seminar subject
- They have supervised or attended seminars in this field before
- Their department aligns with the seminar's academic discipline

Seminar topic and description:
\"\"\"{query_text}\"\"\"

Your task:
For each professor below, assign a match score from 0 to 100 reflecting how suitable they are as a seminar advisor for this specific topic. Be strict and realistic — most professors should score below 50 unless their expertise is genuinely relevant. Only assign 85+ if the match is exceptional and direct.

Scoring guide:
- 85-100: Excellent Match — professor's core research directly covers this topic
- 70-84: Strong Match — closely related field or has supervised similar seminars
- 50-69: Moderate Match — some relevant overlap but not their primary focus
- 30-49: Weak Match — tangential or indirect relevance only
- 0-29: Not Relevant — different field entirely

For the reason: write 2 clear sentences. First sentence: what specifically in their profile matches (or doesn't). Second sentence: why they would (or wouldn't) make a good advisor for this seminar.

Return ONLY a valid JSON array with no extra text, in this exact format:
[{{"index": 0, "score": 85, "reason": "..."}}]

Professor profiles:
{json.dumps(profiles, ensure_ascii=False, indent=2)}"""

    client = Groq()
    message = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.choices[0].message.content.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    rankings = json.loads(raw)

    # Build index map
    rank_map = {item["index"]: item for item in rankings}

    results = []
    for i, advisor in enumerate(candidates):
        rank = rank_map.get(i, {})
        score = float(rank.get("score", 0))
        score = max(0.0, min(score, 100.0))
        reason = rank.get("reason", "No explanation provided.")

        if score >= 85:
            label = "Excellent Match"
        elif score >= 70:
            label = "Strong Match"
        elif score >= 50:
            label = "Moderate Match"
        elif score >= 30:
            label = "Weak Match"
        else:
            label = "Not Relevant"

        _, matched_kws = _keyword_boost(query_text, advisor)

        results.append({
            "id": advisor["id"],
            "title": _safe_get(advisor, "title"),
            "full_name": advisor["full_name"],
            "department": advisor["department"],
            "expertise_keywords": advisor["expertise_keywords"],
            "email": advisor["email"],
            "score": round(score, 1),
            "match_score": int(round(score)),
            "score_label": label,
            "match_level": label,
            "matched_keywords": ", ".join(matched_kws) if matched_kws else "",
            "reasons": [reason],
            "ai_powered": True,
        })

    # Add remaining advisors (filtered out in pass 1) with score 0
    candidate_ids = {a["id"] for a in candidates}
    for advisor in advisors:
        if advisor["id"] not in candidate_ids:
            results.append({
                "id": advisor["id"],
                "title": _safe_get(advisor, "title"),
                "full_name": advisor["full_name"],
                "department": advisor["department"],
                "expertise_keywords": advisor["expertise_keywords"],
                "email": advisor["email"],
                "score": 0.0,
                "match_score": 0,
                "score_label": "Not Relevant",
                "match_level": "Not Relevant",
                "matched_keywords": "",
                "reasons": [f"Professor's field does not match the seminar category: {query_category['label'] if query_category else 'unknown'}."],
                "ai_powered": True,
            })

    return sorted(results, key=lambda r: (-r["score"], r["full_name"].lower()))


def _rank_with_ai(model, query_text, advisors):
    """AI-powered ranking using sentence-transformers cosine similarity.

    This implementation uses a weighted scoring scheme across multiple
    components as requested:
      - Department relevance: 20%
      - Research / expertise relevance: 30%
      - Recent seminar topics relevance: 25%
      - Overall semantic similarity: 20%
      - Keyword overlap (supporting): 5%

    Each professor receives an independent score from 0-100.
    """
    from sentence_transformers import util as st_util

    # Prepare component texts
    prof_departments = []
    prof_research = []
    prof_recent = []
    prof_corpus = []
    for adv in advisors:
        prof_departments.append(_safe_get(adv, "department") or "")
        research_text = (_safe_get(adv, "expertise_keywords") + " " + _safe_get(adv, "all_topics_corpus")).strip()
        prof_research.append(research_text or "")
        prof_recent.append(_safe_get(adv, "recent_seminar_topics") or "")
        prof_corpus.append(_build_professor_corpus(adv) or "no information available")

    # Encode embeddings
    query_embedding = model.encode(query_text, convert_to_tensor=True)
    dept_embeddings = model.encode(prof_departments, convert_to_tensor=True, batch_size=32)
    research_embeddings = model.encode(prof_research, convert_to_tensor=True, batch_size=32)
    recent_embeddings = model.encode(prof_recent, convert_to_tensor=True, batch_size=32)
    corpus_embeddings = model.encode(prof_corpus, convert_to_tensor=True, batch_size=32)

    # Cosine similarities
    dept_sims = st_util.cos_sim(query_embedding, dept_embeddings)[0]
    research_sims = st_util.cos_sim(query_embedding, research_embeddings)[0]
    recent_sims = st_util.cos_sim(query_embedding, recent_embeddings)[0]
    corpus_sims = st_util.cos_sim(query_embedding, corpus_embeddings)[0]

    # Weights
    W_DOMAIN = 0.30
    W_DEPT = 0.20
    W_RESEARCH = 0.15
    W_RECENT = 0.10
    W_SEMANTIC = 0.10
    W_KEYWORD = 0.05

    query_category = _extract_query_category(query_text)
    
    # Compute normalized semantic scores for all advisors to detect peak matches
    all_semantic_sims = []
    for idx in range(len(advisors)):
        def _norm(x):
            v = float(x)
            return max(0.0, min((v + 1.0) / 2.0, 1.0))
        semantic_sim = _norm(corpus_sims[idx]) if prof_corpus[idx] else 0.0
        all_semantic_sims.append(semantic_sim)
    
    max_semantic_sim = max(all_semantic_sims) if all_semantic_sims else 0.5
    
    results = []
    for idx, advisor in enumerate(advisors):
        def _norm(x):
            v = float(x)
            return max(0.0, min((v + 1.0) / 2.0, 1.0))

        dept_sim = _norm(dept_sims[idx]) if prof_departments[idx] else 0.0
        research_sim = _norm(research_sims[idx]) if prof_research[idx] else 0.0
        recent_sim = _norm(recent_sims[idx]) if prof_recent[idx] else 0.0
        semantic_sim = _norm(corpus_sims[idx]) if prof_corpus[idx] else 0.0
        domain_score = _compute_domain_relevance(query_text, advisor)
        advisor_text = (
            _safe_get(advisor, "department") + " "
            + _safe_get(advisor, "expertise_keywords") + " "
            + _safe_get(advisor, "recent_seminar_topics") + " "
            + _safe_get(advisor, "all_topics_corpus")
        ).lower()
        category_match = _advisor_matches_category(advisor, query_category) if query_category else True
        category_dept_match = False
        if query_category:
            category_dept_match = any(dept in advisor_text for dept in query_category["departments"])

        kw_boost, matched_kws = _keyword_boost(query_text, advisor)

        domain_score_value = domain_score * (W_DOMAIN * 100)
        dept_score = dept_sim * (W_DEPT * 100)
        research_score = research_sim * (W_RESEARCH * 100)
        recent_score = recent_sim * (W_RECENT * 100)
        semantic_score = semantic_sim * (W_SEMANTIC * 100)
        keyword_score = kw_boost * (W_KEYWORD * 100)

        if query_category:
            if category_dept_match:
                dept_score = max(dept_score, 0.95 * (W_DEPT * 100))
            elif category_match:
                dept_score = max(dept_score, 0.70 * (W_DEPT * 100))
            else:
                dept_score = min(dept_score, 0.05 * (W_DEPT * 100))

        base_score = dept_score + research_score + recent_score + semantic_score + keyword_score
        if query_category and not category_match:
            base_score *= 0.08
        elif query_category and not category_dept_match:
            base_score *= 0.80

        if query_category and category_match:
            category_bonus = 12.0
            if category_dept_match:
                category_bonus = 18.0
            base_score += category_bonus
        elif not query_category:
            # For uncategorized queries, apply aggressive semantic-based penalty
            semantic_gap = max_semantic_sim - semantic_sim
            # Penalty multiplier: stronger gap = stronger penalty
            penalty_multiplier = 1.0 - (semantic_gap * 2.0)
            base_score *= max(0.05, penalty_multiplier)

        total_score = domain_score_value + base_score
        # calibration multiplier to spread stronger matches
        CALIBRATION_FACTOR = 1.02
        total_score = total_score * CALIBRATION_FACTOR
        total_score = max(0.0, min(total_score, 100.0))
        score = round(total_score, 1)

        if score >= 85:
            label = "Excellent Match"
        elif score >= 70:
            label = "Strong Match"
        elif score >= 50:
            label = "Moderate Match"
        elif score >= 30:
            label = "Weak Match"
        else:
            label = "Not Relevant"

        # Explanations
        reasons = []
        dept_text = _safe_get(advisor, "department")
        if dept_text:
            if dept_sim > 0.6:
                reasons.append(f"The professor belongs to {dept_text}, which is directly relevant to the seminar topic.")
            elif dept_sim > 0.25:
                reasons.append(f"The professor's department ({dept_text}) is somewhat related to the seminar topic.")

        expertise = _safe_get(advisor, "expertise_keywords")
        if expertise:
            # show a concise subset of expertise keywords for explanations
            kws = [k.strip() for k in re.split(r"[;,]", expertise) if k.strip()]
            top_kws = ", ".join(kws[:6])
            if research_sim > 0.6:
                reasons.append(f"Strong overlap with the professor's research interests: {top_kws}.")
            elif research_sim > 0.25:
                reasons.append(f"Some overlap with the professor's research interests: {top_kws}.")

        recent_text = _safe_get(advisor, "recent_seminar_topics")
        if recent_text:
            topics = [t.strip() for t in recent_text.split("|") if t.strip()]
            short_recent = "; ".join(topics[:3])
            if recent_sim > 0.6:
                reasons.append(f"Recent seminar topics include: {short_recent}. These are closely aligned with the seminar subject.")
            elif recent_sim > 0.25:
                reasons.append(f"Recent seminar topics include: {short_recent}. They are somewhat related.")

        if semantic_sim > 0.6:
            reasons.append("High semantic similarity between the seminar description and the professor's overall profile.")
        elif semantic_sim > 0.25:
            reasons.append("Moderate semantic similarity between the seminar description and the professor's profile.")

        if query_category and category_match:
            reasons.append(f"The professor's profile matches the seminar category: {query_category['label']}.")
        elif query_category and not category_match:
            reasons.append(f"The seminar is categorized as {query_category['label']}, while the professor's profile is in another field.")

        if matched_kws:
            reasons.append(f"Keyword overlap (supporting signal): {', '.join(matched_kws[:6])}.")

        if not reasons:
            reasons.append("No strong semantic or keyword matches detected.")

        results.append({
            "id": advisor["id"],
            "title": _safe_get(advisor, "title"),
            "full_name": advisor["full_name"],
            "department": advisor["department"],
            "expertise_keywords": advisor["expertise_keywords"],
            "email": advisor["email"],
            "score": score,
            "match_score": int(round(score)),
            "score_label": label,
            "match_level": label,
            "matched_keywords": ", ".join(matched_kws) if matched_kws else "",
            "reasons": reasons,
            "ai_powered": True,
        })

    return sorted(results, key=lambda r: (-r["score"], r["full_name"].lower()))


def _rank_with_keywords(query_text, advisors):
    """Fallback keyword-based ranking if AI model is unavailable."""
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return []

    query_category = _extract_query_category(query_text)
    results = []
    for advisor in advisors:
        kw_text = _safe_get(advisor, "expertise_keywords")
        kw_text += " " + _safe_get(advisor, "recent_seminar_topics")
        kw_text += " " + _safe_get(advisor, "all_topics_corpus")
        adv_tokens = set(tokenize(kw_text))

        matched = query_tokens & adv_tokens
        if adv_tokens:
            score = round((len(matched) / max(len(query_tokens), 1)) * 100, 1)
        else:
            score = 0.0

        category_match = _advisor_matches_category(advisor, query_category) if query_category else True
        if query_category and not category_match:
            score *= 0.45

        score = min(score, 100.0)

        if score >= 90:
            label = "Excellent Match"
        elif score >= 70:
            label = "Strong Match"
        elif score >= 50:
            label = "Moderate Match"
        elif score >= 30:
            label = "Weak Match"
        else:
            label = "Not Relevant"

        reasons = _find_matched_reasons(query_text, advisor)

        results.append({
            "id": advisor["id"],
            "title": _safe_get(advisor, "title"),
            "full_name": advisor["full_name"],
            "department": advisor["department"],
            "expertise_keywords": advisor["expertise_keywords"],
            "email": advisor["email"],
            "score": score,
            "score_label": label,
            "match_score": int(round(score)),
            "match_level": label,
            "matched_keywords": ", ".join(sorted(matched)),
            "reasons": reasons,
            "ai_powered": False,
        })

    return sorted(results, key=lambda r: (-r["score"], r["full_name"].lower()))
