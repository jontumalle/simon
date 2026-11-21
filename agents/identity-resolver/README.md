# `identity-resolver` (`simon-identity-resolver`)

- **Model:** `gemini-4-argon` (`max_total_tokens: "64000"`)
- **Phase:** A (Sequential Anchor — runs first per `DiscoveryLead`)
- **Pattern:** 2-step sequential (`1a Generic Core -> 1b Domain Extension`)
- **Input:** `DiscoveryLead` from [data/discovery_investigator_contract.json](../../data/discovery_investigator_contract.json)
- **Output:** `IdentityBundle` (`identity_and_contact`, `bio_text`, `primary_genre`, `subgenres[]`, `attribution_status`, `process_trace[]`, `missing_fields[]`)
- **Isolated Eval:** `python3 -m unittest tests.test_investigator_evals.TestIdentityResolverEval`
