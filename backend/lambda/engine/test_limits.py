"""One case per limit, plus a seeded sweep of random batches."""

from __future__ import annotations

import random
import unittest

from limits import HARD_LEVERAGE_CAP, check_batch

REGISTER = {
    "portfolio": {"maxPositionWeightHard": 0.10, "maxSectorWeight": 0.25},
    "execution": {"maxOrderWeight": 0.12, "maxOrdersPerDay": 40},
    "leverage": {"hardCap": 1.5},
}


def _check(**kwargs: object) -> list[str]:
    base = {
        "equity": 100.0,
        "positions": {},
        "orders": [],
        "prices": {"AAA": 10.0},
        "register": REGISTER,
        "target_level": 1.0,
        "universe": {"AAA"},
        "sectors": {"AAA": "tech"},
        "buys_halted": False,
    }
    base.update(kwargs)
    return check_batch(**base)  # type: ignore[arg-type]


class LimitsTest(unittest.TestCase):
    def test_a_clean_batch_passes(self) -> None:
        self.assertEqual(_check(orders=[{"symbol": "AAA", "side": "buy", "quantity": 1, "thesisId": "t"}]), [])

    def test_exposure_blocks_a_buy(self) -> None:
        # 20 shares * 10 = 200 on equity 100 is 2.0 times.
        reasons = _check(orders=[{"symbol": "AAA", "side": "buy", "quantity": 20, "thesisId": "t"}])
        self.assertIn("exposure", reasons)

    def test_a_sell_is_allowed_while_exposure_is_above_the_cap(self) -> None:
        reasons = _check(
            positions={"AAA": 20},
            orders=[{"symbol": "AAA", "side": "sell", "quantity": 1, "thesisId": "t"}],
        )
        self.assertEqual(reasons, [])

    def test_each_check(self) -> None:
        self.assertTrue(any(item.startswith("position:") for item in _check(
            orders=[{"symbol": "AAA", "side": "buy", "quantity": 2, "thesisId": "t"}],
            register={**REGISTER, "portfolio": {"maxPositionWeightHard": 0.10, "maxSectorWeight": 1}},
            target_level=1.5,
        )))
        self.assertIn("negative_quantity", _check(orders=[{"symbol": "AAA", "side": "sell", "quantity": 1, "thesisId": "t"}]))
        self.assertTrue(any(item.startswith("missing_thesis") for item in _check(
            orders=[{"symbol": "AAA", "side": "buy", "quantity": 1}]
        )))
        self.assertIn("buys_halted", _check(
            orders=[{"symbol": "AAA", "side": "buy", "quantity": 1, "thesisId": "t"}],
            buys_halted=True,
        ))
        self.assertTrue(any(item.startswith("outside_universe") for item in _check(
            orders=[{"symbol": "AAA", "side": "buy", "quantity": 1, "thesisId": "t"}],
            universe=set(),
        )))

    def test_random_clean_batches_stay_at_or_below_the_cap(self) -> None:
        rng = random.Random(1)
        for _ in range(1000):
            equity = 100.0
            price = 10.0
            quantity = rng.randint(0, 20)
            orders = [{"symbol": "AAA", "side": "buy", "quantity": quantity, "thesisId": "t"}] if quantity else []
            reasons = check_batch(
                equity, {}, orders, {"AAA": price}, REGISTER, 1.5,
                universe={"AAA"}, sectors={"AAA": "tech"}, buys_halted=False,
            )
            if reasons:
                continue
            exposure = quantity * price / equity
            self.assertLessEqual(exposure, HARD_LEVERAGE_CAP)


if __name__ == "__main__":
    unittest.main()
