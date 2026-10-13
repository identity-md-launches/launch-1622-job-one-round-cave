# Call Witness — contribution 24

Local checks on 2026-10-13. They document this contribution and are not independent certification.

| Check | Result |
| --- | --- |
| `python3 -B -m unittest discover -s line-4/tools/call-witness -p 'test_*.py' -v` | Exit 0; 8 tests passed. |
| `python3 -B line-4/tools/call-witness/call_witness.py demo` | Exit 0; replayed the saved real ZTO witness and reported `agree`. |
| `live --block 0x18f8d21` | Exit 2 / `inconclusive`; both providers agreed on the old finalized header, dRPC returned ZTO supply, and PublicNode reported its historical state unavailable. This is correctly not presented as agreement. |
| PNG structure | 1254 × 1254, non-interlaced RGB 8-bit PNG; SHA-256 `ab7d97ec7725f46784e68707d69ab3ab7a2f17b42600cbe1c38a0d3a502d4da3`. |
| JPEG structure | Baseline 3-component JFIF JPEG, 512 × 512, 57,373 bytes. |
| Record shape | Record 24 has the required six traits, numeric number `24`, and uses the PNG digest in its artifact URL. |

`Call Witness` now accepts `live --block <hex>` and requires both public providers to have finalized and agree on that exact header before calling either contract. The new unit cases cover explicit shared-block selection and rejection when the requested block is newer than either finalized head. No keys, wallet files, environment variables, signatures, payments, broadcasts or deployments were used.
