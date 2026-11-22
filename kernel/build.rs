//! Build script for prost code generation from protobuf schemas.

use std::env;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-env-changed=PROTOC");
    println!("cargo:rerun-if-env-changed=PROTOC_INCLUDE");
    if env::var_os("PROTOC").is_none() {
        env::set_var("PROTOC", protoc_bin_vendored::protoc_bin_path()?);
        if env::var_os("PROTOC_INCLUDE").is_none() {
            env::set_var("PROTOC_INCLUDE", protoc_bin_vendored::include_path()?);
        }
    }
    let out_dir = PathBuf::from(env::var("OUT_DIR")?);
    let proto_dir = PathBuf::from("../protos");

    // Check if proto directory exists
    if !proto_dir.exists() {
        println!(
            "cargo:warning=Proto directory not found at {:?}, skipping codegen",
            proto_dir
        );
        return Ok(());
    }

    let proto_files = [
        proto_dir.join("reckon/record.proto"),
        proto_dir.join("reckon/budget.proto"),
        proto_dir.join("reckon/causality.proto"),
        proto_dir.join("reckon/events.proto"),
    ];

    // Only compile if all proto files exist
    let all_exist = proto_files.iter().all(|p| p.exists());
    if !all_exist {
        println!("cargo:warning=Not all proto files found, skipping codegen");
        return Ok(());
    }

    // Configure prost-build
    let mut config = prost_build::Config::new();
    config
        .out_dir(&out_dir)
        .type_attribute(".", "#[derive(serde::Serialize, serde::Deserialize)]")
        .type_attribute(".", "#[serde(rename_all = \"camelCase\")]");

    // Compile protos
    config.compile_protos(&proto_files, &[&proto_dir])?;

    // Re-run if protos change
    for proto in &proto_files {
        println!("cargo:rerun-if-changed={}", proto.display());
    }

    Ok(())
}
