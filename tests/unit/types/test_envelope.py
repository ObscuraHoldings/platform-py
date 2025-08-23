from platform_py.types.envelope import ulid, envelope, EventEnvelope


def test_ulid_generates_26_char_crockford_base32_strings():
    id1 = ulid()
    id2 = ulid()
    assert isinstance(id1, str) and isinstance(id2, str)
    assert len(id1) == 26 and len(id2) == 26
    assert id1 != id2


def test_envelope_builder_sets_required_fields():
    env = envelope(topic="intent.submitted", payload={"foo": "bar"}, correlation_id="intent:123")
    assert isinstance(env, EventEnvelope)
    assert env.topic == "intent.submitted"
    assert env.correlationId == "intent:123"
    assert env.payload == {"foo": "bar"}
    assert env.eventId and len(env.eventId) == 26
