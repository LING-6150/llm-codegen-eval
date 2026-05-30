import pytest

from llm_codegen_eval.core.case import CodeType, EvalCase, ElementCheck
from llm_codegen_eval.core.runner import _EVALUATORS
from llm_codegen_eval.evaluators.html_eval import HtmlEvaluator
from llm_codegen_eval.evaluators.vue_eval import VueEvaluator


def vue_case() -> EvalCase:
    return EvalCase(
        case_id="vue_test",
        prompt="Build a Vue app",
        code_type=CodeType.VUE_PROJECT,
        required_checks=[
            ElementCheck(
                type="regex_match",
                pattern="package\\.json",
                description="Project includes package.json",
            ),
            ElementCheck(
                type="regex_match",
                pattern="task.*?list|v-for",
                description="Task list exists",
            ),
            ElementCheck(
                type="text_contains",
                expected="Add Task",
                description="Add task copy exists",
            ),
        ],
        optional_checks=[
            ElementCheck(
                type="regex_match",
                pattern="modal|dialog",
                description="Modal UI exists",
            ),
        ],
        forbidden_patterns=["eval\\s*\\("],
    )


@pytest.mark.asyncio
async def test_vue_evaluator_passes_delimited_project_text():
    code = """
package.json
```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "vite": "^5.0.0"
  }
}
```

src/App.vue
```vue
<template>
  <aside>Tasks</aside>
  <ul>
    <li v-for="task in tasks" :key="task.id">{{ task.title }}</li>
  </ul>
  <button>Add Task</button>
  <dialog>New task modal</dialog>
</template>
<script setup>
import { ref } from 'vue'
const tasks = ref([{ id: 1, title: 'Task list item' }])
</script>
```

src/main.js
```js
import { createApp } from 'vue'
import App from './App.vue'
createApp(App).mount('#app')
```
"""

    result = await VueEvaluator().evaluate(code, vue_case())

    assert result.passed is True
    assert result.required_passed == 3
    assert result.optional_passed == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_vue_evaluator_fails_missing_detectable_structure():
    code = """
<div class="task-list">
  <button>Add Task</button>
</div>
"""

    result = await VueEvaluator().evaluate(code, vue_case())

    assert result.passed is False
    assert result.required_passed == 2
    assert "Missing package.json" in result.error
    assert "Missing src/App.vue" in result.error


@pytest.mark.asyncio
async def test_vue_evaluator_handles_plain_project_text():
    code = """
The project contains package.json with dependencies: { "vue": "^3.5.0" }.
The main component is src/App.vue:
<template><section><h1>Task list</h1><button>Add Task</button></section></template>
<script setup>import { ref } from 'vue'; const tasks = ref([])</script>
"""

    result = await VueEvaluator().evaluate(code, vue_case())

    assert result.passed is True
    assert result.required_passed == 3


def test_runner_maps_vue_project_to_vue_evaluator():
    assert _EVALUATORS[CodeType.VUE_PROJECT] is VueEvaluator
    assert _EVALUATORS[CodeType.VUE_PROJECT] is not HtmlEvaluator
