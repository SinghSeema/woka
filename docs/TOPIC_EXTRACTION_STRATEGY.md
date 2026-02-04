# Topic Extraction Strategy

## Current Approach: Keyword-Based (Active)

**Status**: ✅ **In Production**

**Implementation**: `backend/bot/services/topic_extractor.py`

**How It Works:**
- Maintains a vocabulary of wellness topics (`WELLNESS_TOPICS`)
- Extracts topics using pattern matching and word boundary detection
- Focuses on user messages only (not assistant responses)
- Filters out generic terms unless explicitly mentioned

**Pros:**
- ✅ Fast (<1ms)
- ✅ No API costs
- ✅ Predictable and debuggable
- ✅ Works well for common wellness topics

**Cons:**
- ❌ Requires manual vocabulary updates
- ❌ Misses synonyms and variations
- ❌ Can't understand context
- ❌ Doesn't scale to new domains

**Maintenance:**
- Add new topics to `WELLNESS_TOPICS` set in `topic_extractor.py`
- Current categories: Sleep, Nutrition, Exercise, Mental Health, Physical Health, Habits, Medical, Hobbies

**When to Use:**
- Current production system
- Fast topic extraction needed
- Common wellness topics

---

## Future Approach: Fine-Tuned SBERT (Planned)

**Status**: 📋 **Planned for Future**

**Target Timeline**: 3-6 months (after collecting training data)

**Why Fine-Tuning:**
- Automatic topic understanding (no manual vocabulary)
- Handles synonyms and variations semantically
- Understands domain context
- Scales without manual updates

**See**: `docs/FINETUNING_SBERT_FOR_WELLNESS.md` for detailed plan

---

## Migration Path

1. **Phase 1 (Current)**: Keyword-based approach
2. **Phase 2 (Data Collection)**: Collect training data from sessions
3. **Phase 3 (Fine-Tuning)**: Train SBERT on wellness data
4. **Phase 4 (Deployment)**: A/B test and gradually migrate
5. **Phase 5 (Hybrid)**: Use fine-tuned model with keyword fallback

