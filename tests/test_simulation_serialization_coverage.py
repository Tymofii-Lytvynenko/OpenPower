from src.simulation.serialization import to_plain_data


def test_plain_serialization_hex_encodes_bytes_and_preserves_unknown_values():
    marker = object()

    result = to_plain_data({"blob": b"\x00\xff", "extension": marker})

    assert result["blob"] == "00ff"
    assert result["extension"] is marker
