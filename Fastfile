default_platform(:ios)

platform :ios do
  desc "Build the iOS app"
  lane :build do
    # Synchronize signing certificates and profiles using match
    match(
      type: "appstore", # Change to "development" or "adhoc" if needed
      readonly: true    # Use readonly mode if you're not modifying profiles
    )

    # Build the app using gym
    gym(
      scheme: "myapp-ios", # Scheme name
      workspace: "myapp-ios/myapp.xcodeproj/project.xcworkspace", # Workspace path
      configuration: "Release", # Use "Debug" for development builds
      export_method: "app-store", # Use "ad-hoc" or "development" if needed
      export_team_id: "MNGTD992QD", # Team ID for signing
      output_directory: "myapp-ios/build", # Output directory for the IPA
      output_name: "myapp.ipa", # Output file name
      clean: true, # Clean build before building
      export_options: {
        provisioningProfiles: {
          "com.snslocation.electricians-now" => "match AppStore com.snslocation.electricians-now" # Adjust based on your provisioning profile
        }
      }
    )
  end
end