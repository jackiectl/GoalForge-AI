"""Parse FIFA 2026 Annex C (third-place allocation, 495 combinations) into configs/annex_c.json.

Source: Wikipedia "Template:2026 FIFA World Cup third-place table" raw wikitext, which mirrors
Annex C of the official FIFA World Cup 2026 Regulations (verified against the PDF, incl. the
actual-2026 row 67). Each row: the 8 groups whose third-placed teams advanced -> which third
each of the 8 hosting group winners (1A,1B,1D,1E,1G,1I,1K,1L) plays in the round of 32.

    python scripts/parse_annex_c.py <thirds_wikitext.txt>

Output: {"hosts": ["A","B","D","E","G","I","K","L"],
         "table": {"BDEFIJKL": ["E","J","B","D","I","F","L","K"], ... 495 entries}}
Key = the 8 advancing groups sorted+joined; value = third's group per host, in hosts order.
"""
import json
import re
import sys

HOSTS = ["A", "B", "D", "E", "G", "I", "K", "L"]      # group winners that face a third (Art 12.6)


def main():
    text = open(sys.argv[1]).read()
    rows = re.split(r"!\s*scope=\"row\"\s*\|\s*(\d+)", text)[1:]   # [num, body, num, body, ...]
    table = {}
    for num, body in zip(rows[::2], rows[1::2]):
        advancing = re.findall(r"'''([A-L])'''", body)
        assigns = re.findall(r"\b3([A-L])\b", body)
        assert len(advancing) == 8, f"row {num}: {len(advancing)} advancing groups"
        assert len(assigns) == 8, f"row {num}: {len(assigns)} assignments"
        key = "".join(sorted(advancing))
        assert sorted(assigns) == sorted(advancing), f"row {num}: assigns != advancing"
        for host, third in zip(HOSTS, assigns):
            assert host != third, f"row {num}: 1{host} vs 3{third} (own group)"
        table[key] = assigns
    assert len(table) == 495, f"{len(table)} unique combinations (expected 495)"
    # spot-check the real 2026 outcome: thirds from B,D,E,F,I,J,K,L -> row 67
    assert table["BDEFIJKL"] == ["E", "J", "B", "D", "I", "F", "L", "K"]
    out = {"hosts": HOSTS, "table": table}
    json.dump(out, open("configs/annex_c.json", "w"), indent=0)
    print(f"parsed {len(table)} combinations -> configs/annex_c.json")


if __name__ == "__main__":
    main()
