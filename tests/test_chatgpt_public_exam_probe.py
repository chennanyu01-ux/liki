import json
import os
import subprocess
import time
import urllib.request


def _call(cli, env, fn, args):
    p = subprocess.run(
        ["python3", cli],
        input=json.dumps({"fn": fn, "args": args}, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=60,
    )
    data = json.loads(p.stdout.decode("utf-8"))
    assert data.get("ok"), data.get("error")
    return data["data"]


def test_chatgpt_public_exam_probe():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    engine_dir = os.path.join(root, "engine")
    engine_bin = "/tmp/liki-engine-chatgpt"
    subprocess.run(
        ["go", "build", "-o", engine_bin, "./cmd/liki/"],
        cwd=engine_dir,
        check=True,
        timeout=180,
    )
    proc = subprocess.Popen([engine_bin, "-addr", ":18082"])
    try:
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:18082/health", timeout=1).read()
                break
            except Exception:
                time.sleep(1)
        else:
            raise AssertionError("Liki engine did not become ready")

        env = dict(os.environ, LIKI_RPC_URL="http://127.0.0.1:18082/jsonrpc")
        cli = os.path.join(root, "skills", "liki-divination", "tools", "agent_cli.py")
        snapshot = _call(cli, env, "liuyao_snapshot", {
            "question": "2026年年底参加国家公务员考试，以及2027年年初参加省考或事业编考试，这一轮考试最终成功上岸的整体可能性大不大？",
            "mode": "auto",
            "matter": "study",
            "topic": "study",
        })
        overall = _call(cli, env, "liuyao_ask", {
            "snapshot": snapshot,
            "message": "判断这一轮国考、省考、事业编最终上岸的整体倾向。重点解释用神、世爻、原神忌神、动爻和关键冲合空破。不要给确定百分比，只判断机会偏大、中等还是偏小，以及达成需要哪些条件。",
        })
        compare = _call(cli, env, "liuyao_ask", {
            "snapshot": snapshot,
            "message": "仍基于同一卦，比较2026年年底国考与2027年年初省考或事业编，哪一阶段更容易出现实质性进展或上岸信号？只做条件性倾向，不重新起卦。",
        })
        payload = {
            "snapshot": snapshot,
            "overall": overall,
            "compare": compare,
        }
        raise AssertionError("CHATGPT_PUBLIC_EXAM_RESULT=" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
