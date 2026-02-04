// Copy to config.js for local testing (DO NOT COMMIT config.js)
// In AWS deployment, CodeBuild generates config.js from CloudFormation outputs.
window.__CONFIG__ = {
  apiBaseUrl: "https://<api-id>.execute-api.eu-central-1.amazonaws.com",
  cognitoDomain: "https://<domain-prefix>.auth.eu-central-1.amazoncognito.com",
  cognitoClientId: "<cognito-app-client-id>",
  redirectUri: "https://<cloudfront-domain>/",
};
