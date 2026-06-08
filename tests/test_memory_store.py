from data_governance_agent_runtime.memory.store import RuntimeMemory


def test_runtime_memory_compacts_to_recent_facts() -> None:
    memory = RuntimeMemory()
    memory.remember("first", "old")
    memory.remember("second", "current")

    compacted = memory.compact(max_items=1)

    assert compacted == {"second": "current"}
    assert memory.facts == {"second": "current"}

