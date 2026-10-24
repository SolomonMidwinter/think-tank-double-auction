"""Mock model wrapper for free end-to-end testing of the simulation harness.

Model name format: "mock" or "mock-fail<N>" (fail from round N onward, to
rehearse credit exhaustion / API failure mid-run).
"""
import json
import random
import re
from typing import List

from src.resources.model_wrappers import Message, ModelWrapper


class MockClient(ModelWrapper):
    def __init__(self, model_name: str, **kwargs):
        kwargs.pop("response_format", None)
        super().__init__(model_name, **kwargs)
        m = re.match(r"mock-fail(\d+)", model_name)
        self.fail_from_round = int(m.group(1)) if m else None
        self.rng = random.Random(0)

    def _round_number(self, prompt: str) -> int:
        m = re.search(r"This is Hour #(\d+)", prompt)
        return int(m.group(1)) if m else 1

    def generate(self, messages: List[Message]) -> str:
        prompt = messages[-1]["content"]
        round_num = self._round_number(prompt)
        if self.fail_from_round is not None and round_num >= self.fail_from_round:
            # Mimic model_wrappers behavior on persistent API errors (e.g. 402
            # out-of-credits): the real clients log and return None.
            return None

        is_seller = "as a seller" in prompt
        is_buyer = "as a buyer" in prompt
        if is_seller:
            price = round(self.rng.uniform(94.0, 98.0) - 0.15 * round_num, 2)
            resp = {
                "reflection": f"Mock reflection for hour {round_num}.",
                "plan_for_this_hour": "Mock plan: track the spread.",
                "ask": price,
                "new_memory": f"Hour {round_num}: asked {price}.",
                "scratch_pad_update": "#### Observations\nmock",
            }
            if "Messages Received from Other Sellers" in prompt:
                resp["plan_for_message"] = "Mock message plan."
                resp["message_to_sellers"] = f"mock hello from hour {round_num}"
        elif is_buyer:
            price = round(self.rng.uniform(82.0, 86.0) + 0.15 * round_num, 2)
            resp = {
                "reflection": f"Mock reflection for hour {round_num}.",
                "plan_for_this_hour": "Mock plan: creep bids up.",
                "bid": price,
                "new_memory": f"Hour {round_num}: bid {price}.",
                "scratch_pad_update": "#### Observations\nmock",
            }
        else:  # overseer or eval prompt
            resp = {"coordination": "no", "coordination_score": 1, "score": 1,
                    "type": None, "evidence": []}
        return json.dumps(resp)

    def batch_generate(self, messages_list: List[List[Message]]) -> List[str]:
        return [self.generate(m) for m in messages_list]
