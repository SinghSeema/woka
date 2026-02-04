# Fine-Tuning Sentence-BERT for Wellness Domain - Implementation Plan

**Status**: 📋 Planned for Future Implementation  
**Current Approach**: Keyword-based topic extraction (see `docs/TOPIC_EXTRACTION_STRATEGY.md`)  
**Target Timeline**: 3-6 months (after collecting sufficient training data)

---

## The Problem with Keyword-Based Approach

**Current Limitation:**
- Manual vocabulary maintenance
- Misses synonyms and variations
- Can't understand context ("reading books" vs "reading a room")
- Requires constant updates for new topics
- Doesn't capture semantic relationships

**Example:**
- User says: "I want to start meditating"
- Keyword approach: Might miss if "meditation" not in vocabulary
- Fine-tuned SBERT: Understands "meditating" = "meditation" semantically

## Why Fine-Tuning SBERT Makes Sense

### Benefits

1. **Automatic Topic Understanding**
   - Learns that "reading" = "books" = "literature" semantically
   - Understands context: "reading books" (hobby) vs "reading symptoms" (medical)
   - Captures domain-specific relationships

2. **Scalability**
   - No manual vocabulary updates
   - Handles new topics automatically
   - Learns from your data

3. **Better Semantic Search**
   - More accurate similarity scores
   - Better query matching
   - Domain-specific embeddings

4. **Fewer False Positives**
   - Understands context better
   - Distinguishes wellness topics from general conversation

### Trade-offs

**Pros:**
- ✅ Scalable (no manual updates)
- ✅ Better accuracy
- ✅ Handles synonyms/variations
- ✅ Domain-specific understanding

**Cons:**
- ❌ Requires training data
- ❌ Training time/compute
- ❌ Model versioning
- ❌ More complex deployment

## Fine-Tuning Strategy

### Option 1: Fine-Tune on Wellness Conversations (Recommended)

**Training Data:**
- Your session summaries
- User queries about wellness topics
- Wellness domain texts (articles, guides)

**Approach:**
```python
# Use sentence-transformers fine-tuning
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# Load base model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Prepare training data
# Format: (anchor, positive, negative) triplets
# Example:
# - Anchor: "I want to start reading books"
# - Positive: "reading hobby books literature"
# - Negative: "exercise workout fitness"

train_examples = [
    InputExample(texts=["I want to start reading", "reading books hobby"]),
    InputExample(texts=["I'm interested in meditation", "meditation mindfulness"]),
    # ... more examples
]

# Fine-tune
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.CosineSimilarityLoss(model)
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    output_path='./wellness-sbert-model'
)
```

### Option 2: Use Domain-Specific Pre-Trained Model

**Already Available Models:**
- `sentence-transformers/all-MiniLM-L6-v2` (current - general purpose)
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (multilingual)
- `sentence-transformers/all-mpnet-base-v2` (better quality, larger)

**Health/Wellness Specific:**
- BioBERT (biomedical)
- ClinicalBERT (clinical)
- No general wellness model exists (opportunity!)

### Option 3: Hybrid Approach (Best for Now)

**Keep keyword-based for:**
- Fast exact matches
- Explicit topic filtering
- Fallback when embeddings uncertain

**Add fine-tuned SBERT for:**
- Semantic topic extraction
- Better query understanding
- Synonym/variation handling

## Implementation Plan

### Phase 1: Collect Training Data (Current)

**What to Collect:**
1. Session summaries with topics
2. User queries with extracted topics
3. Wellness domain texts

**Format:**
```json
{
  "text": "I want to start reading books as a hobby",
  "topics": ["reading", "books", "hobby"],
  "category": "hobbies"
}
```

### Phase 2: Fine-Tune Model

**Steps:**
1. Prepare training data (triplets: anchor, positive, negative)
2. Fine-tune `all-MiniLM-L6-v2` on wellness data
3. Evaluate on test set
4. Compare with base model

**Training Time:**
- Small dataset (1000 examples): ~30 minutes
- Medium dataset (10,000 examples): ~2-3 hours
- Large dataset (100,000 examples): ~1 day

### Phase 3: Deploy Fine-Tuned Model

**Integration:**
1. Replace base model with fine-tuned model
2. Keep same API (`generate_embedding()`)
3. Monitor performance
4. A/B test if needed

## Alternative: Few-Shot Learning (Faster)

Instead of full fine-tuning, use **few-shot learning** with better prompts:

```python
# Use LLM to extract topics with few-shot examples
def extract_topics_with_llm(user_message: str) -> List[str]:
    prompt = f"""
    Extract wellness topics from this user message.
    
    Examples:
    - "I want to start reading books" → ["reading", "books", "hobby"]
    - "Let's talk about zumba classes" → ["zumba", "exercise", "fitness"]
    - "I'm interested in meditation" → ["meditation", "mindfulness"]
    
    User message: "{user_message}"
    Topics:
    """
    # Call LLM (Groq) to extract topics
    # More flexible than keyword matching
```

**Pros:**
- ✅ No training needed
- ✅ Handles new topics automatically
- ✅ Uses existing LLM infrastructure

**Cons:**
- ❌ Slower (LLM call)
- ❌ More expensive (API costs)
- ❌ Less consistent than fine-tuned model

## Recommendation

### Short-term (Now)
1. **Keep keyword-based approach** (works for common topics)
2. **Add more keywords** (reading, hobbies, etc.) as needed
3. **Use LLM for edge cases** (few-shot topic extraction for unknown topics)

### Medium-term (1-2 months)
1. **Collect training data** from your sessions
2. **Fine-tune SBERT** on wellness conversations
3. **A/B test** fine-tuned vs base model

### Long-term (3-6 months)
1. **Deploy fine-tuned model** as primary
2. **Keep keyword-based** as fast path
3. **Continuous learning** (retrain periodically with new data)

## Training Data Requirements

**Minimum:**
- 500-1000 examples (can work with less)
- Balanced across topics
- High quality (manually reviewed)

**Ideal:**
- 10,000+ examples
- Diverse topics
- Real user conversations

**Your Current Data:**
- Session summaries (good source!)
- User queries (excellent source!)
- Topics already extracted (can use as labels)

## Quick Win: Better Pre-Trained Model

**Before fine-tuning, try:**
```python
# Upgrade to better base model
LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
# or
LOCAL_EMBEDDING_MODEL = "sentence-transformers/paraphrase-mpnet-base-v2"
```

**Trade-off:**
- Better quality embeddings
- Slightly larger model (768 dim vs 384)
- Still no domain-specific knowledge

## Implementation Roadmap

### Phase 1: Data Collection (Months 1-2)

**Goal**: Collect 5,000-10,000 training examples

**Data Sources:**
1. **Session Summaries** (Primary)
   - Extract: summary text + topics (already extracted)
   - Format: `(summary, topics)` pairs
   - Expected: ~100-200 examples per week

2. **User Queries** (Secondary)
   - Extract: user message + topics
   - Format: `(query, topics)` pairs
   - Expected: ~50-100 examples per week

3. **Wellness Domain Texts** (Augmentation)
   - Wellness articles, guides, documentation
   - Format: `(text, topics)` pairs
   - Expected: ~1,000-2,000 examples

**Data Format:**
```json
{
  "text": "I want to start reading books as a hobby",
  "topics": ["reading", "books", "hobby"],
  "source": "user_query",
  "session_id": "abc123"
}
```

**Storage:**
- Create `training_data/topic_extraction/` directory
- Store as JSONL (one example per line)
- Version control (git) for tracking

**Tools Needed:**
- Script to export sessions with topics
- Script to validate and clean data
- Script to format for training

### Phase 2: Model Fine-Tuning (Month 3)

**Goal**: Fine-tune `all-MiniLM-L6-v2` on wellness topic extraction

**Training Setup:**
```python
# File: scripts/finetune_wellness_sbert.py
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader

# 1. Load base model
model = SentenceTransformer('all-MiniLM-L6-v2')

# 2. Prepare training data
# Format: (anchor, positive) pairs
# Example: ("I want to start reading", "reading books hobby")
train_examples = load_training_data()

# 3. Fine-tune
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=16)
train_loss = losses.CosineSimilarityLoss(model)

model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=100,
    output_path='./models/wellness-sbert-v1'
)

# 4. Evaluate
test_results = evaluate_model(model, test_data)
```

**Training Requirements:**
- GPU: Recommended (CUDA), but can use CPU (slower)
- Time: ~2-3 hours for 10K examples on GPU
- Memory: ~4GB RAM

**Evaluation Metrics:**
- Topic extraction accuracy
- Semantic similarity improvement
- Query matching performance

### Phase 3: Integration (Month 3-4)

**Goal**: Integrate fine-tuned model into production

**Changes Needed:**
1. Update `embedding_service.py` to load fine-tuned model
2. Create new `topic_extractor_sbert.py` for semantic topic extraction
3. Add feature flag: `USE_SBERT_TOPIC_EXTRACTION`
4. A/B test: Compare keyword vs SBERT extraction

**Integration Points:**
- `backend/bot/services/topic_extractor.py` → Add SBERT option
- `backend/bot/services/summary_service.py` → Use SBERT if enabled
- `backend/bot/services/intent_detector.py` → Use SBERT for topic extraction

**Rollout Strategy:**
1. Deploy with feature flag OFF (keyword-based)
2. Enable for 10% of sessions (A/B test)
3. Monitor metrics (extraction quality, performance)
4. Gradually increase to 100%
5. Keep keyword-based as fallback

### Phase 4: Monitoring & Iteration (Ongoing)

**Metrics to Track:**
- Topic extraction accuracy
- Number of topics extracted per session
- User satisfaction (if measurable)
- Model performance (latency, memory)

**Iteration:**
- Retrain quarterly with new data
- Version models (v1, v2, etc.)
- Compare new vs old model performance

## Training Data Collection Script

**File**: `scripts/collect_training_data.py`

```python
"""
Collect training data from sessions for SBERT fine-tuning.
Exports session summaries + topics as training examples.
"""
import json
from pathlib import Path
from bot.services.database_service import get_all_sessions

def collect_training_data(output_file: str = "training_data/topic_extraction/sessions.jsonl"):
    """Collect session summaries with topics as training data."""
    # Get all sessions from database
    # Format: (summary, topics) pairs
    # Save as JSONL
    pass
```

## Fine-Tuning Script Template

**File**: `scripts/finetune_wellness_sbert.py`

```python
"""
Fine-tune Sentence-BERT on wellness topic extraction.
"""
# See full implementation in FINETUNING_SBERT_FOR_WELLNESS.md
```

## Success Criteria

**Before Fine-Tuning:**
- ✅ 5,000+ training examples collected
- ✅ Data validated and cleaned
- ✅ Baseline metrics established

**After Fine-Tuning:**
- ✅ Topic extraction accuracy > 85%
- ✅ Handles new topics without manual updates
- ✅ Semantic similarity improved by 10%+
- ✅ No performance regression (<100ms latency)

## Conclusion

**Current Strategy**: Keep keyword-based approach (works well, fast, no costs)

**Future Strategy**: Fine-tune SBERT when:
1. ✅ Have 5,000+ training examples
2. ✅ Keyword approach becomes limiting
3. ✅ Ready to invest in model training

**The keyword approach is a solid interim solution** while collecting data for fine-tuning. No rush to migrate - fine-tune when you have the data and see clear benefits.

