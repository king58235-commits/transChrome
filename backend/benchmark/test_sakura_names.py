"""Member-name accuracy with the Sakura backend, for every glossary.MEMBERS
entry in three short sentences (full name, and a nickname in two templates):

  A  names replaced with Chinese inside the Japanese text (the old MADLAD way)
  B  names left as spoken, passed as Sakura glossary entries (production)
  C  no glossary

A sentence counts as correct when the expected display name appears in the
final Traditional Chinese output. 2026-09-26 (Sakura-7B iq4xs, llama.cpp
b11200): A 203/259, B 240/259, C 26/259. B's misses were mostly the
Latin display names (Kyoko, Tsuzuri, Sopia, Michiru, Sayaka, Yuki...), which
Sakura tends to rewrite in Chinese.

Needs the backend stopped (uses the same llama-server port). From backend/:
    venv\\Scripts\\python.exe benchmark\\test_sakura_names.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import glossary
import sakura
import translator


def sentences():
    out = []
    for forms, _zh in glossary.MEMBERS:
        full = forms[0].rstrip("~")
        nick = next((f.rstrip("~") for f in forms[1:]), full)
        nick = nick if nick.endswith(("ちゃん", "ち", "ん", "ろん")) else nick + "ちゃん"
        out += [f"{full}の配信見た?", f"昨日{nick}とコラボしたんだけど、めっちゃ面白かった", f"{nick}が言ってたよ"]
    return [s for s in out if glossary.name_entries(s)]


def main():
    translator.BACKEND = "sakura"
    translator.load_model()
    to_tw = translator._converter
    runs = {
        "A replace in text": lambda ja: sakura.generate(glossary.apply(ja)),
        "B glossary entries": lambda ja: sakura.generate(glossary.apply(ja, replace_names=False), [
            (src, translator._to_simplified.convert(dst)) for src, dst in glossary.name_entries(ja)]),
        "C no glossary": lambda ja: sakura.generate(ja),
    }
    cases = sentences()
    for label, run in runs.items():
        misses = []
        for ja in cases:
            out = glossary.fix_output(to_tw.convert(run(ja)))
            want = [dst for _, dst in glossary.name_entries(ja)]
            if not all(w in out for w in want):
                misses.append(f"   {ja} => {out}  (want {want})")
        print(f"{label}: {len(cases) - len(misses)}/{len(cases)}")
        if label.startswith("B"):
            print("\n".join(misses))


if __name__ == "__main__":
    main()
