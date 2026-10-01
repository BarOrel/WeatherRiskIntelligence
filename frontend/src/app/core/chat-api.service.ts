import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ChatRequest, ChatResponse, Conversation, Hub, SessionSummary } from './api.models';

@Injectable({ providedIn: 'root' })
export class ChatApiService {
  private readonly http = inject(HttpClient);

  chat(request: ChatRequest): Promise<ChatResponse> {
    return firstValueFrom(this.http.post<ChatResponse>('/chat', request));
  }

  hubs(): Promise<Hub[]> {
    return firstValueFrom(this.http.get<Hub[]>('/hubs'));
  }

  /** Stored conversations, most recently active first. */
  sessions(): Promise<SessionSummary[]> {
    return firstValueFrom(this.http.get<SessionSummary[]>('/chat/sessions'));
  }

  /** One stored conversation with every answer and its evidence. */
  conversation(sessionId: string): Promise<Conversation> {
    return firstValueFrom(this.http.get<Conversation>(`/chat/sessions/${encodeURIComponent(sessionId)}`));
  }
}

/** Turns an API failure into a message a business user understands. */
export function friendlyError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) {
    return 'Something went wrong. Please try again.';
  }
  const detail = typeof error.error?.detail === 'string' ? error.error.detail : '';
  switch (error.status) {
    case 0:
      return "Can't reach the Weather Risk service. Please check that the server is running.";
    case 422:
      return `That question couldn't be processed${detail ? `: ${detail}` : '.'}`;
    case 503:
      return `The AI assistant is not available right now. ${detail}`.trim();
    case 504:
      return 'The AI assistant took too long to respond. Please try again.';
    case 502:
      return 'The AI assistant returned an unexpected response. Please try again.';
    default:
      return detail || `The service returned an error (${error.status}). Please try again.`;
  }
}
