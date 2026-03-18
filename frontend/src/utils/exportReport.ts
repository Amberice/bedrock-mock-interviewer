function downloadFile(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = window.URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  window.URL.revokeObjectURL(url);
}

function safeString(value: unknown, fallback = "N/A") {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function exportSessionJson(sessionData: unknown) {
  if (!sessionData) {
    alert("No session data available to export.");
    return;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `stellar-session-${timestamp}.json`;

  downloadFile(
    filename,
    JSON.stringify(sessionData, null, 2),
    "application/json"
  );
}

export function exportSessionMarkdown(sessionData: any) {
  if (!sessionData) {
    alert("No session data available to export.");
    return;
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `stellar-report-${timestamp}.md`;

  const overallScore =
    sessionData?.scorecard?.overall_score ??
    sessionData?.overall_score ??
    sessionData?.score ??
    "N/A";

  const recommendation =
    sessionData?.scorecard?.recommendation ??
    sessionData?.recommendation ??
    "N/A";

  const transcript =
    sessionData?.transcript ??
    sessionData?.conversation ??
    sessionData?.messages ??
    "N/A";

  const feedback =
    sessionData?.feedback ??
    sessionData?.scorecard?.summary ??
    "N/A";

  const markdown = `# Stellar Interview Report

## Summary
- **Overall Score:** ${safeString(overallScore)}
- **Recommendation:** ${safeString(recommendation)}

## Feedback
${safeString(feedback)}

## Transcript
\`\`\`
${safeString(transcript)}
\`\`\`

## Full Response
\`\`\`json
${JSON.stringify(sessionData, null, 2)}
\`\`\`
`;

  downloadFile(filename, markdown, "text/markdown");
}