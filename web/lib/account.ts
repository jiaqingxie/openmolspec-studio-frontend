export interface CreditBalance {
  available: number;
  reserved: number;
}

export interface Account {
  authenticated: boolean;
  mock_enabled: boolean;
  identities: { id: string; name: string }[];
  user?: { id: string; nickname: string };
  credits?: CreditBalance;
}

export interface Usage extends CreditBalance {
  entries: {
    task_id?: string;
    created_at: string;
    operation: string;
    source: string;
    amount: number;
    status: string;
    rule_version: string;
    duration_ms?: number | null;
    usage?: Record<string, unknown> | null;
  }[];
}

export interface AccessToken {
  id: string;
  name: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface McpEndpoints {
  local_url: string | null;
  cloud_url: string | null;
}
