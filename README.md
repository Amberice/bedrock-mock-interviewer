# Stellar Interviewer 🚀

Stellar Interviewer is an AI-powered mock interview application built with **React + Vite + TypeScript** on the frontend and **AWS serverless services** on the backend. It simulates interview conversations, returns AI-generated feedback, and now supports **client-side export of structured interview session artifacts** such as scorecards, transcripts, and markdown reports.

---

## Overview

This project was built as a full-stack portfolio application to demonstrate:

- conversational AI workflow design
- serverless application architecture on AWS
- frontend state management and UX design
- speech input/output integration
- structured evaluation/report generation
- deployable production web app patterns with PWA support

The application allows a user to interact with an AI interviewer, receive scored feedback, and export interview results for later review.

---

## Core Capabilities

- **AI mock interview chat** powered by Amazon Bedrock
- **Persistent conversation memory** with DynamoDB-backed session tracking
- **Speech-to-text input** using the Web Speech API
- **Audio playback** for assistant responses
- **Progressive Web App (PWA)** support for installable/mobile-friendly experience
- **Structured feedback output** including score, feedback, transcript, and scorecard fields
- **Client-side session export** to JSON and Markdown

---

### High-level architecture
```text
User
  ↓
React + Vite + TypeScript Frontend
  ↓
AWS API Gateway
  ↓
AWS Lambda
  ↓
Amazon Bedrock (Nova Micro)
  ↓
DynamoDB (session memory / chat history)

---

## Repository structure
- `frontend/` – React + Vite + TypeScript client
- `frontend/src/components/ChatInterface.tsx` – primary chat UI and interaction flow
- `frontend/src/utils/exportReport.ts` – client-side export utilities
- `backend/` – Lambda application logic and Bedrock integration
- `cdk/` – infrastructure as code for AWS resources

---

## Key implementation decisions
- **Client-side export generation:** Chosen to avoid introducing a separate reporting service or export endpoint. This keeps report generation fast, lightweight, and decoupled from backend rendering logic.
- **Session-aware payload handling:** The frontend persists the full `/chat` response in local state so evaluation artifacts such as scorecards and transcripts can be reused for multiple UI actions without additional round trips.
- **Serverless backend architecture:** Lambda + API Gateway was selected to keep the app operationally light while integrating Bedrock inference and DynamoDB-backed session memory.
- **PWA support:** Added to improve mobile usability and make the app installable without requiring a native client.

---

## Tradeoffs and current limitations
- Exported reports are generated from the most recent in-memory session payload and are not yet persisted as downloadable historical artifacts in a backend store.
- Browser-native speech features simplify implementation, but support and behavior vary across browsers.
- Session continuity exists at the chat level, but richer historical session browsing is not yet implemented in the frontend.

---