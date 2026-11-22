//! Build script for Reckon daemon - generates gRPC code from protos

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("cargo:rerun-if-env-changed=PROTOC");
    println!("cargo:rerun-if-env-changed=PROTOC_INCLUDE");
    if std::env::var_os("PROTOC").is_none() {
        std::env::set_var("PROTOC", protoc_bin_vendored::protoc_bin_path()?);
        if std::env::var_os("PROTOC_INCLUDE").is_none() {
            std::env::set_var("PROTOC_INCLUDE", protoc_bin_vendored::include_path()?);
        }
    }
    // Compile the proto files for tonic
    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .type_attribute(".", "#[derive(serde::Serialize)]")
        .type_attribute(".", "#[serde(rename_all = \"camelCase\")]")
        .compile(
            &[
                "../protos/reckon/core/v1/types.proto",
                "../protos/reckon/core/v1/service.proto",
            ],
            &["../protos"],
        )?;

    Ok(())
}
