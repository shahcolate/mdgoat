# Examples

Three sample documents that show what mdgoat does. Try the commands below.

| File | What it demonstrates |
|------|----------------------|
| `clean-doc.md` | A healthy document — scores 100/100 A+. |
| `messy-conversion.md` | Typical PDF/OCR damage: mojibake, hyphenation breaks, repeated headers, a broken table. |
| `poisoned-contract.md` | A weaponized document: hidden HTML-comment injection, Unicode tag-block ASCII smuggling, invisible characters, an exfiltration beacon image, and a homoglyph word. |

```bash
# Score all three at a glance
mdgoat score examples/*.md

# See exactly what's hidden in the poisoned contract
mdgoat scan examples/poisoned-contract.md

# Watch the messy conversion get repaired
mdgoat clean examples/messy-conversion.md --diff
```

The poisoned and messy files were generated with exact attack bytes, so they
are the real thing — not screenshots. That is the point: none of it is visible
in a rendered preview, but mdgoat reads what the model reads.
