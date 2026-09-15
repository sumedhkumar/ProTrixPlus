from __future__ import annotations

from app.config import WorkerConfig


def test_mock_worker_keeps_shared_default_consumer_group(monkeypatch) -> None:
    monkeypatch.delenv("PROTRIX_EXECUTION_ADAPTER", raising=False)
    monkeypatch.delenv("PROTRIX_SIGNAL_CONSUMER_GROUP", raising=False)
    config = WorkerConfig.from_env()
    assert config.consumer_group == "protrix-workers"


def test_mt5_worker_routes_every_account_to_its_own_group(monkeypatch) -> None:
    monkeypatch.setenv("PROTRIX_EXECUTION_ADAPTER", "mt5")
    monkeypatch.setenv("PROTRIX_MT5_USER_EMAIL", "Bob.Trader+one@example.test")
    monkeypatch.delenv("PROTRIX_SIGNAL_CONSUMER_GROUP", raising=False)
    monkeypatch.delenv("PROTRIX_WORKER_NAME", raising=False)
    config = WorkerConfig.from_env()
    assert config.consumer_group == "protrix-workers-mt5-bob-trader-one-example-test"
    assert config.consumer_name == "worker-mt5-bob-trader-one-example-test"


def test_explicit_group_and_worker_name_are_preserved(monkeypatch) -> None:
    monkeypatch.setenv("PROTRIX_EXECUTION_ADAPTER", "mt5")
    monkeypatch.setenv("PROTRIX_SIGNAL_CONSUMER_GROUP", "protrix-workers-gold")
    monkeypatch.setenv("PROTRIX_WORKER_NAME", "worker-gold")
    config = WorkerConfig.from_env()
    assert config.consumer_group == "protrix-workers-gold"
    assert config.consumer_name == "worker-gold"
