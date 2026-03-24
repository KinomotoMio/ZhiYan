# Slidev Provider Failure Classification

## Situation

Issue `#212` addresses a stability gap in the Slidev MVP: upstream model calls can fail not only with retryable HTTP errors, but also with malformed or truncated provider responses such as incomplete tool calls.

## Candidate Rule

- The provider adapter should retry a bounded number of times for malformed provider responses, just like it already does for transient retryable HTTP status codes.
- Not every `UnexpectedModelBehavior` is a malformed response; malformed/truncated provider output should be classified separately from generic unexpected provider behavior.
- Provider-malformed failures should be classified at the Slidev orchestration boundary, not leaked as raw provider exceptions.
- Slidev request validation failures and upstream provider failures must stay separate:
  - validation failures -> `422`-style contract errors
  - provider malformed failures -> stable provider reason codes, surfaced as upstream errors
- API responses should preserve a machine-friendly reason code so callers can distinguish retryable upstream instability from deck contract failures.

## Why It Matters

If malformed provider responses are treated as generic validation failures, consumers cannot tell whether they should repair the deck input or just retry generation. Keeping this boundary explicit makes the harness more diagnosable:

- adapter = retry transient/malformed provider behavior
- Slidev service = classify provider failure into product-facing reason codes
- API = preserve stable machine-readable failure details

## Reuse Guidance

When another harness flow depends on external model/tool providers:

1. Retry bounded malformed-response failures at the adapter edge.
2. Translate exhausted provider failures into product-facing reason codes before they escape the feature service.
3. Do not collapse provider instability into user-input validation errors.
4. Keep HTTP/network retry logic and malformed-response retry logic visible in tests.
