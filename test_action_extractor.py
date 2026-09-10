import unittest

from engine.action_extractor import extract_actions


class ActionExtractorTests(unittest.TestCase):
    def test_japanese_multiple_actions_and_raw_preservation(self):
        message = (
            "USER: A案とB案を比較し、A案を採用する。一方でB案は採用しない。"
            "表示を旧UIから新UIへ変更する。理由は入力の確認が容易になるため。"
            "変更前: 旧UI\n変更後: 新UI\n"
            + "補足として、この内容は評価対象の根拠を明確にするために記録します。" * 16
        )
        actions = extract_actions(message)
        self.assertGreater(len(message), 500)
        self.assertGreaterEqual(len(actions), 5)
        self.assertTrue(all(action["raw_message"] == message.split("USER: ", 1)[1] for action in actions))
        self.assertIn(("adoption", "positive"), {(a["type"], a["polarity"]) for a in actions})
        self.assertIn(("rejection", "negative"), {(a["type"], a["polarity"]) for a in actions})
        self.assertIn(("comparison", "neutral"), {(a["type"], a["polarity"]) for a in actions})
        self.assertTrue(any(a["type"] == "revision" and a["before"] and a["after"] for a in actions))
        self.assertTrue(any(a["type"] == "reason" or a["reason"] for a in actions))

    def test_english_multiple_actions_and_raw_preservation(self):
        message_body = (
            "Compare option X and option Y, adopt option X, but do not adopt option Y. "
            "Change from the old interface to the new interface because the review is clearer. "
            "Before: old interface\nAfter: new interface\n" +
            "This sentence records the explicit evidence and rationale without adding any inferred fact. " * 30
        )
        message = "USER: " + message_body + "\nASSISTANT: acknowledged"
        actions = extract_actions(message)
        self.assertGreater(len(message_body), 2000)
        self.assertTrue(all(action["raw_message"] == message_body + "\n" for action in actions))
        self.assertIn(("adoption", "positive"), {(a["type"], a["polarity"]) for a in actions})
        self.assertIn(("rejection", "negative"), {(a["type"], a["polarity"]) for a in actions})
        self.assertIn(("comparison", "neutral"), {(a["type"], a["polarity"]) for a in actions})
        self.assertTrue(any(a["type"] == "revision" and a["before"] and a["after"] for a in actions))

    def test_ordinary_chat_is_not_forced_into_action(self):
        self.assertEqual(extract_actions("USER: Hello, how are you?\nASSISTANT: Fine."), [])


if __name__ == "__main__":
    unittest.main()
