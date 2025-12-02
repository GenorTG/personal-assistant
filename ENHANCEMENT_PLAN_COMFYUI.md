# Enhancement Plan: ComfyUI llama-cpp-python Client Features

## Overview
Integrate advanced features and better UI organization inspired by the ComfyUI llama-cpp-python client extension.

## Missing Parameters to Add

### 1. Logit Bias
- **Parameter**: `logit_bias` (Dict[int, float])
- **Description**: Bias specific token IDs (positive = more likely, negative = less likely)
- **Use Case**: Force or prevent specific tokens/words
- **Implementation**: Add to SamplerSettings schema and UI

### 2. Penalty Range
- **Parameter**: `penalty_range` (int)
- **Description**: Range of tokens to apply repetition penalty to
- **Use Case**: Fine-tune repetition control
- **Implementation**: Add to SamplerSettings

### 3. Penalty Alpha (Contrastive Search)
- **Parameter**: `penalty_alpha` (float)
- **Description**: Contrastive search penalty
- **Use Case**: Advanced generation control
- **Implementation**: Add to SamplerSettings

### 4. Num Predict (Alias)
- **Parameter**: `num_predict` (int, alias for max_tokens)
- **Description**: Alternative name for max_tokens
- **Implementation**: Support both names

### 5. N Probs
- **Parameter**: `n_probs` (int)
- **Description**: Return top N token probabilities
- **Use Case**: Debugging and analysis
- **Implementation**: Add as optional debug feature

### 6. Penalty Present/Freq (Alternative to presence/frequency_penalty)
- **Parameters**: `penalty_present`, `penalty_freq`
- **Description**: Alternative naming for penalties
- **Implementation**: Support both naming conventions

## UI/UX Improvements

### 1. Better Parameter Grouping
- **Current**: All parameters in one long list
- **Proposed**: Group into collapsible sections:
  - **Basic Sampling**: temperature, top_p, top_k, min_p
  - **Repetition Control**: repeat_penalty, presence_penalty, frequency_penalty, repeat_last_n, penalty_range
  - **Advanced Sampling**: typical_p, tfs_z, penalty_alpha
  - **Mirostat**: mirostat_mode, mirostat_tau, mirostat_eta
  - **Output Control**: max_tokens, stop, seed, grammar
  - **Advanced**: logit_bias, n_probs

### 2. Visual Presets
- **Current**: Basic presets (default, creative, precise, etc.)
- **Proposed**: 
  - Visual preset cards with descriptions
  - Custom preset saving/loading
  - Preset preview (shows which parameters are changed)

### 3. Parameter Tooltips
- **Current**: Basic descriptions
- **Proposed**: 
  - Rich tooltips with examples
  - Links to documentation
  - Recommended ranges based on model type

### 4. Real-time Validation
- **Current**: Basic validation
- **Proposed**:
  - Real-time parameter interaction warnings
  - Suggestions when parameters conflict
  - Visual indicators for parameter relationships

### 5. Advanced Features Panel
- **Current**: All advanced in one section
- **Proposed**:
  - Separate "Advanced" tab with:
    - Logit bias editor (token ID → bias value)
    - Grammar editor (GBNF syntax highlighting)
    - Debug mode (show probabilities, token IDs)

## Implementation Plan

### Phase 1: Add Missing Parameters
1. Update `SamplerSettings` schema in backend
2. Update `ChatRequest` schema to include new parameters
3. Update `SamplerSettings` dataclass in `services/gateway/src/services/llm/sampler.py`
4. Update frontend `SamplerSettingsContext` and component

### Phase 2: UI Improvements
1. Reorganize `SamplerSettings.tsx` with collapsible sections
2. Add visual preset cards
3. Enhance tooltips with rich content
4. Add parameter validation and warnings

### Phase 3: Advanced Features
1. Add logit bias editor component
2. Add grammar editor with syntax highlighting
3. Add debug mode toggle
4. Add preset save/load functionality

## Files to Modify

### Backend
- `services/gateway/src/api/schemas.py` - Add new parameters
- `services/gateway/src/services/llm/sampler.py` - Update dataclass
- `services/gateway/src/api/routes.py` - Pass new parameters to LLM

### Frontend
- `services/frontend/contexts/SamplerSettingsContext.tsx` - Add new fields
- `services/frontend/components/SamplerSettings.tsx` - Reorganize UI
- `services/frontend/lib/types.ts` - Add new types

## Benefits
1. **More Control**: Access to all llama-cpp-python server features
2. **Better UX**: Organized, intuitive interface
3. **Power User Features**: Advanced options for fine-tuning
4. **Consistency**: Match industry-standard tools like ComfyUI


