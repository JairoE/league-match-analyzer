# Request Flow: Sign In to Home

This document outlines the high-level request flow for the `league-match-analyzer` application, specifically illustrating how microservices and technologies interact when a user signs in and loads their match history on the home page.

## System Components

*   **Frontend**: Next.js 16 (React Server Components + Client Hooks)
*   **Backend**: FastAPI (Async Python)
*   **Worker**: ARQ (Async Redis Queue)
*   **Infrastructure**: PostgreSQL (Data), Redis (Cache/Queue/Rate Limits)
*   **External**: Riot Games API

## High-Level Flow Diagram

```mermaid
graph TD
  %% Nodes
  User((User))
  
  subgraph Frontend ["Next.js Frontend"]
    SignIn["SignInForm"]
    Home["Home Page"]
    Fetch["Fetch API (api.ts)"]
  end
  
  subgraph Backend ["FastAPI Service"]
    AuthRoute["Auth Router"]
    MatchRoute["Match Router"]
    Service["Business Logic"]
  end
  
  subgraph Infra ["Infrastructure"]
    DB[("PostgreSQL")]
    Redis[("Redis")]
  end
  
  subgraph Workers ["Background Worker"]
    ARQ["ARQ Worker"]
  end
  
  subgraph External ["Riot Games"]
    Riot["Riot API"]
  end

  %% Sign In Flow
  User -- "1. Credentials" --> SignIn
  SignIn -- "2. POST /auth/login" --> AuthRoute
  AuthRoute --> Service
  Service -- "3. Validate/Link" --> DB
  Service -- "4. Fetch Profile" --> Riot
  AuthRoute -- "5. Auth Response" --> SignIn
  SignIn -- "6. Redirect" --> Home

  %% Home Page Flow
  Home -- "7. Load Matches" --> Fetch
  Fetch -- "8. GET /matches" --> MatchRoute
  MatchRoute --> Service
  
  %% Sync Logic
  Service -- "9. Check Cache/DB" --> DB
  Service -- "10. Rate Limit Check" --> Redis
  Service -- "11. Fetch Match IDs" --> Riot
  
  %% Background Task (Async)
  Service -. "12. Enqueue Details" .-> Redis
  Redis -. "13. Pull Job" .-> ARQ
  ARQ -. "14. Fetch Details" .-> Riot
  ARQ -. "15. Update Record" .-> DB
  
  %% Response
  Service -- "16. Return Data" --> MatchRoute
  MatchRoute --> Fetch
  Fetch -- "17. Render UI" --> Home
```

## detailed Technology Stack Flow

### 1. Frontend Layer
*   **Next.js & React**: The `/home` page initializes. `useEffect` triggers data fetching.
*   **Fetch API**: `api.ts` handles the HTTP request, checking the client-side cache first.

### 2. API Layer
*   **FastAPI**: Receives the request on `/riot-accounts/{id}/matches`.
*   **Service Layer**: Orchestrates data retrieval. It checks **PostgreSQL** for existing data and queries the **Riot API** for updates.
*   **Rate Limiting**: The `RiotApiClient` uses **Redis** to track request quotas and prevent 429 errors.

### 3. Asynchronous Processing
*   **ARQ & Redis**: Heavy operations (fetching full match details) are offloaded. The API enqueues a job into **Redis**.
*   **Worker Service**: A separate process picks up the job, fetches data from **Riot**, and performs an upsert into **PostgreSQL**.
