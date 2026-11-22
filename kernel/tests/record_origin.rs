use prost::Message;
use reckon_kernel::proto::{MemoryRecord, RecordOrigin};

#[test]
fn record_origin_keeps_the_embedded_wire_shape() {
    // Captured before the type rename; every origin field is present.
    let wire: &[u8] = b"\x52\x1f\x0a\x05write\x12\x01a\x12\x01b\x1a\x100123456789abcdef";
    let record = MemoryRecord::decode(wire).unwrap();
    assert_eq!(
        record.provenance,
        Some(RecordOrigin {
            source_op: "write".into(),
            input_ids: vec!["a".into(), "b".into()],
            hash: "0123456789abcdef".into(),
        })
    );
    assert_eq!(record.encode_to_vec(), wire);
    assert_eq!(
        serde_json::to_value(&record).unwrap()["provenance"],
        serde_json::json!({
            "sourceOp": "write", "inputIds": ["a", "b"], "hash": "0123456789abcdef"
        })
    );
}
