"""Human-readable reference id generators, all seeded from the caller's rng
so a full dataset generation run is reproducible end to end."""

import random


def customer_ref(rng: random.Random) -> str:
    return f"CUS-{rng.randint(1000, 9999)}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"


def account_ref(rng: random.Random) -> str:
    return f"ACC-{rng.randint(10000, 99999)}"


def txn_ref(rng: random.Random) -> str:
    return f"TXN-{rng.randint(10**9, 10**10 - 1)}"


def external_counterparty_ref(rng: random.Random) -> str:
    return f"EXT-{rng.randint(100000, 999999)}"


class RefRegistry:
    """Tracks every reference string issued during a generation run, and
    can be preloaded with what's already in the database. Without this,
    two runs sharing an rng seed (e.g. re-running `generate-data` with its
    default --seed against a database `seed --if-empty` already populated)
    would deterministically replay the exact same ref sequence and collide
    on the unique constraints instead of just risking a rare collision."""

    def __init__(self) -> None:
        self.customer_refs: set[str] = set()
        self.account_refs: set[str] = set()
        self.txn_refs: set[str] = set()

    @staticmethod
    def _unique(rng: random.Random, generator, used: set[str]) -> str:
        ref = generator(rng)
        while ref in used:
            ref = generator(rng)
        used.add(ref)
        return ref

    def new_customer_ref(self, rng: random.Random) -> str:
        return self._unique(rng, customer_ref, self.customer_refs)

    def new_account_ref(self, rng: random.Random) -> str:
        return self._unique(rng, account_ref, self.account_refs)

    def new_txn_ref(self, rng: random.Random) -> str:
        return self._unique(rng, txn_ref, self.txn_refs)
