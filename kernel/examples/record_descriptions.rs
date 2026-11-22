//! Emit descriptions derived from the laboratory model, never from a fixture.
use reckon_kernel::record;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let kind = std::env::args().nth(1).unwrap_or_else(|| "schema".into());
    match kind.as_str() {
        "schema" => println!("{}", serde_json::to_string_pretty(&record::json_schema())?),
        "typescript" => print!("{}", record::typescript()),
        "bundle" => println!(
            "{}",
            serde_json::json!({
                "schema": record::json_schema(), "typescript": record::typescript(),
            })
        ),
        _ => return Err("expected schema, typescript or bundle".into()),
    }
    Ok(())
}
