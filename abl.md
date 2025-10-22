# ABL+ MVP — Concept & Flow (Expanded Draft)

> **Purpose in one line**  
> Help aspirants close the gap between *what they think they know* and *what they actually know*—faster—by turning every MCQ attempt into actionable insight.

---

## 1. Why “Attempt-Based” Matters  

| Element | Reason it matters | How ABL+ operationalises it |
|---------|-------------------|-----------------------------|
| **Attempt** (user action) | Under **Urooj Law** — *Result = Kismet × Effort* — the one variable users fully control is *Effort*. We surface, record, and analyse that effort at the level of each click. | Every question answered records a 6-point vector (see § 3).|
| **Question** | A well-designed question compresses an entire concept and exposes knowledge gaps instantly. | ABL+ curates PYQs & AI-variants mapped to syllabus nodes, maximising signal-to-noise. |
| **Feedback Loop** | Learning accelerates when feedback is immediate, specific, and measurable. | The system re-routes users to practice, revisit concepts, or challenge themselves based on live attempt data. |

---

## 2. Modes & Their Distinct Utilities  

| Mode | Core Intent | User Mindset | System Behaviour | Typical Use-case |
|------|-------------|--------------|------------------|------------------|
| **Learn** (soon) | Discover a new concept through guided examples. | *Exploratory* | Shows worked examples, hints, and linked reading. | First exposure to a topic. |
| **Practice** | **Solidify** & **reinforce** facts, concepts, and applications at any granularity. | *Deliberate rehearsal* | Unlimited attempts, spaced-repetition surfacing, gentle timers, partial scoring, instant explanations. | Daily drills, weak-area workouts. |
| **Test** | **Diagnose** current mastery in a time-pressured, exam-realistic setting. | *Performance* | Locked answers, exam timer, no hints; post-submission analytics. | Full-length mocks, sectionals, or topic-wise checkpoints. |

> **Why the split?**  
> Both modes involve “solving questions”, but **Practice** optimises for *learning efficiency*, whereas **Test** optimises for *measurement fidelity*. Mixing the two dilutes both benefits.

---

## 3. The 6-Point Attempt Vector  

Each question-attempt is stored as:

| Dimension | Possible Values | Purpose |
|-----------|-----------------|---------|
| **Attempt Type** | `Sureshot`, `Applied`, `Guesswork` | Captures the *confidence & reasoning* behind the click. |
| **Result** | `Correct`, `Wrong` | Binary outcome. |
| **Composite** | 3 × 2 = **6 states** | Drives granular analytics (e.g., *Guesswork-Correct* = lucky; *Sureshot-Wrong* = dangerous misconception). |

We can later extend with **Time Taken**, **Explanation Viewed?**, etc., but the v0.1 six-state model already powers:

- Knowledge zone colour coding.  
- Risk profiling (accuracy vs. confidence).  
- Adaptive question routing.

---

## 4. Knowledge Boundaries & Zones  

| Zone | Colour | Trigger condition (rules of thumb) | Meaning | Action prescribed by ABL+ |
|------|--------|------------------------------------|---------|---------------------------|
| **Green – Known** | ✅ Green | ≥ 3 *Sureshot-Correct* in last 5 attempts, < 20 % error rate overall. | Consolidated knowledge. | Occasional spaced review only. |
| **Blue – Uncertain** | 🔵 Blue | Mixed *Applied* / *Guesswork*, accuracy 40–80 %. | Needs more reps & context. | Push to *Practice* with scaffolded hints. |
| **Grey – Unseen** | ⚪️ Grey | No recorded attempts. | Unknown territory. | Nudge user to explore; prioritise if exam-relevant. |
| **Red – Misconception** | ❌ Red | ≥ 2 *Sureshot-Wrong* in last 3 attempts. | Confident but consistently wrong. | Show “Fix it” mini-lesson; force reflection; highlight in dashboard. |

> **Dynamic Zones**  
> Boundaries update after every attempt, so users *see* their knowledge map breathe and shift — a visual incentive to keep pushing colours toward green.

---

## 5. End-to-End User Journey (MVP)  

1. **Sign-in & Select Exam Year** → Pre-loaded PYQs appear.  
2. **Dashboard** shows colour-coded syllabus tree (+ quick links to weakest zones).  
3. **Choose Mode**  
   - *Practice* defaults to weakest Blue/Red nodes.  
   - *Test* lets user pick Full-length, Subject, or Topic mocks.  
4. **Attempt Loop**  
   - Question → Confidence tag (S/A/G) → Option click → Immediate or deferred feedback per mode.  
   - Vector stored; zones recalculated.  
5. **Reflect Panel** (post-session)  
   - Heat-map, time per question, Red-flags list.  
   - Micro-suggestions: “Review Article 123 – Fundamental Duties” etc.  
6. **Next-step Nudges** appear on dashboard: e.g., “10-min Practice Drill on Polity-Local Gov Red zone”.

---

## 6. Value Delivered  

| Stakeholder | “What I do” on ABL+ | “What I get” |
|-------------|--------------------|--------------|
| **Aspirant** | Attempt questions, tag confidence, review analyses. | A living map of strengths & blind-spots; data-driven daily plan; faster score gains. |
| **Mentor / SME** (future) | Monitor cohort dashboards. | Pinpoint where learners falter; design interventions quickly. |
| **Platform** | Collect structured attempt data. | Flywheel for personalised recommendations & content generation. |

---

## 7. Philosophical Backing  

> **Urooj Law**: *Result = Kismet × Effort*  
> ABL+ cannot (and should not) game destiny, but it can 10× the *leverage* on the only controllable factor — **Effort**. Every coloured cell, every nudge, every insight is a mirror held up to the learner’s own attempts, helping them deploy effort where it compounds the most.

---

### Next Steps for MVP Build

1. **Finalize Attempt schema** in DB (`QuestionLog`, `TopicAttemptSummary`).  
2. **Implement Practice/Test toggles** with HTMX partials for snappy UX.  
3. **Render real-time colour overlays** on syllabus tree (Alpine.js state store).  
4. **Ship a closed alpha** to 20 power users; iterate on confusion points.  

---

*This document is a living artefact. Feel free to annotate or request deeper dives on any section as development proceeds.*
