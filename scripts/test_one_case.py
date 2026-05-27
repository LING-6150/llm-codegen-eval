"""Quick test: run one EvalCase against the Java service."""

import asyncio
from llm_codegen_eval.core.case import EvalCase, ElementCheck, CodeType, Difficulty
from llm_codegen_eval.core.runner import run_case
from llm_codegen_eval.clients.java_client import JavaServiceClient

TEST_CASE = EvalCase(
    case_id="html_005_test",
    prompt="Create a personal profile page with a dark background, including an avatar, name, a one-line introduction, and three skill tags",
    code_type=CodeType.HTML,
    difficulty=Difficulty.MEDIUM,
    required_checks=[
        ElementCheck(
            type="tag_exists",
            selector="img",
            description="Avatar image present"
        ),
        ElementCheck(
            type="tag_exists",
            selector="h1, h2",
            description="Name as heading"
        ),
        ElementCheck(
            type="tag_count",
            selector=".skill-tag, .tag, li, .skill, span.tag",
            expected=3,
            description="At least 3 skill tags"
        ),
    ],
    optional_checks=[
        ElementCheck(
            type="attr_exists",
            selector="img",
            attribute="alt",
            description="Avatar has alt text"
        ),
    ],
    forbidden_patterns=[
        r"eval\s*\(",
        r"document\.write",
        r"innerHTML\s*=",
    ]
)

async def main():
    print("=" * 60)
    print("Starting eval test...")
    print("=" * 60)

    client = JavaServiceClient()

    print("\n[1] Logging in...")
    await client.login()
    print("    Login successful")

    print(f"\n[2] Running case: {TEST_CASE.case_id}")
    print(f"    Prompt: {TEST_CASE.prompt[:80]}...")

    result = await run_case(TEST_CASE, client)

    print("\n[3] Result:")
    print(f"    Passed:               {result.passed}")
    print(f"    Score:                {result.score}/100")
    print(f"    Required:             {result.required_passed}/{result.required_total}")
    print(f"    Optional:             {result.optional_passed}/{result.optional_total}")
    print(f"    Forbidden found:      {result.forbidden_found}")
    print(f"    Generation duration:  {result.generation_duration_ms}ms")
    print(f"    Review score:         {result.review_score}")
    print(f"    Review passed:        {result.review_passed}")
    print(f"    Error:                {result.error}")

    if result.required_failed:
        print("\n[4] Required checks that failed:")
        for check in result.required_failed:
            print(f"    - {check.description}")

    print("\n[5] Generated code preview (first 500 chars):")
    print(result.generated_code[:500])

if __name__ == "__main__":
    asyncio.run(main())
