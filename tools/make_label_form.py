"""Build tools/label_golden.html from the golden CSV. The form exports golden_labels.json; nothing is sent anywhere."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.io import read_source
from pipeline.labels import SHORT_TEXT_CHARS

src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/golden_50_to_label.csv")
rows = [{"id": r["review_id"], "t": r["review_text"]} for r in read_source(src)]  # star ratings deliberately hidden
tpl = Path(__file__).with_name("label_form_template.html").read_text(encoding="utf-8")
out = tpl.replace("__REVIEWS__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")).replace("__SHORT__", str(SHORT_TEXT_CHARS))
Path(__file__).with_name("label_golden.html").write_text(out, encoding="utf-8")
print(f"wrote tools/label_golden.html with {len(rows)} reviews")
