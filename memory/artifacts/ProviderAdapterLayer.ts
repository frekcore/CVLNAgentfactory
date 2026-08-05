// ============================================================================
// Provider Adapter Layer — CVLN Agent Factory
// Interface unifiée pour l'abstraction des modèles IA
// Résout F-006 : Vendor lock-in / Pas d'orchestration multi-modèles
// ============================================================================

// ─── Types fondamentaux ───

export interface IAIResponse {
  content: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model: string;
  provider: string;
  latencyMs: number;
  finishReason: 'stop' | 'length' | 'error' | 'content_filter';
  metadata?: Record<string, unknown>;
}

export interface IAIStreamChunk {
  content: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
  };
  finishReason?: 'stop' | 'length' | 'error' | 'content_filter';
}

export interface IEmbedding {
  vector: number[];
  model: string;
  dimensions: number;
}

export interface IModelParams {
  temperature?: number;      // 0.0 - 2.0
  maxTokens?: number;
  topP?: number;
  frequencyPenalty?: number;
  presencePenalty?: number;
  stopSequences?: string[];
  tools?: IAgentTool[];      // Function calling
}

export interface IAgentTool {
  name: string;
  description: string;
  parameters: object;        // JSON Schema
}

export interface IProviderHealth {
  status: 'healthy' | 'degraded' | 'down';
  latencyMs: number;
  lastChecked: Date;
  errorRate: number;
}

export interface ICostEstimate {
  provider: string;
  model: string;
  estimatedCostUsd: number;
  currency: 'USD';
}

export interface IProviderConfig {
  apiKey: string;
  baseUrl?: string;
  defaultModel: string;
  fallbackModel?: string;
  timeoutMs: number;
  retryPolicy: {
    maxRetries: number;
    backoffMs: number;
  };
}

// ─── Interface principale ───

export interface IAIProvider {
  readonly name: string;
  readonly version: string;
  readonly supportedModels: string[];

  /** Génération de texte complète (non-streaming) */
  generate(
    prompt: string,
    context?: string[],
    params?: IModelParams
  ): Promise<IAIResponse>;

  /** Génération de texte en streaming */
  stream(
    prompt: string,
    context?: string[],
    params?: IModelParams,
    onChunk?: (chunk: IAIStreamChunk) => void
  ): Promise<IAIResponse>;

  /** Génération d'embeddings pour RAG / Vector Store */
  embed(texts: string[]): Promise<IEmbedding[]>;

  /** Vérification de santé du provider */
  healthCheck(): Promise<IProviderHealth>;

  /** Estimation du coût avant appel */
  getCostEstimate(promptTokens: number, model?: string): ICostEstimate;

  /** Initialisation avec configuration */
  initialize(config: IProviderConfig): Promise<void>;

  /** Nettoyage des ressources */
  dispose(): Promise<void>;
}

// ============================================================================
// IMPLEMENTATION : KimiAdapter (Moonshot AI)
// ============================================================================

export class KimiAdapter implements IAIProvider {
  readonly name = 'kimi';
  readonly version = '1.0.0';
  readonly supportedModels = [
    'kimi-k1',
    'kimi-k1.5',
    'kimi-moonshot-v1',
    'kimi-moonshot-v1-8k',
    'kimi-moonshot-v1-32k',
    'kimi-moonshot-v1-128k'
  ];

  private config!: IProviderConfig;
  private client: any; // HttpClient

  async initialize(config: IProviderConfig): Promise<void> {
    this.config = config;
    // Initialisation du client HTTP Moonshot AI
    this.client = new HttpClient({
      baseURL: config.baseUrl || 'https://api.moonshot.cn/v1',
      headers: { 'Authorization': `Bearer ${config.apiKey}` },
      timeout: config.timeoutMs
    });
  }

  async generate(
    prompt: string,
    context?: string[],
    params?: IModelParams
  ): Promise<IAIResponse> {
    const startTime = Date.now();

    const messages = this.buildMessages(prompt, context);

    const response = await this.client.post('/chat/completions', {
      model: params?.model || this.config.defaultModel,
      messages,
      temperature: params?.temperature ?? 0.7,
      max_tokens: params?.maxTokens,
      top_p: params?.topP,
      stop: params?.stopSequences,
      tools: params?.tools?.map(t => ({
        type: 'function',
        function: {
          name: t.name,
          description: t.description,
          parameters: t.parameters
        }
      }))
    });

    const data = response.data;
    const choice = data.choices[0];

    return {
      content: choice.message.content,
      usage: {
        promptTokens: data.usage.prompt_tokens,
        completionTokens: data.usage.completion_tokens,
        totalTokens: data.usage.total_tokens
      },
      model: data.model,
      provider: this.name,
      latencyMs: Date.now() - startTime,
      finishReason: this.mapFinishReason(choice.finish_reason),
      metadata: { kimiSpecific: data.kimi_metadata }
    };
  }

  async stream(
    prompt: string,
    context?: string[],
    params?: IModelParams,
    onChunk?: (chunk: IAIStreamChunk) => void
  ): Promise<IAIResponse> {
    const startTime = Date.now();
    let fullContent = '';
    let totalTokens = 0;

    const messages = this.buildMessages(prompt, context);

    const stream = await this.client.post('/chat/completions', {
      model: params?.model || this.config.defaultModel,
      messages,
      stream: true,
      temperature: params?.temperature ?? 0.7,
      max_tokens: params?.maxTokens
    }, { responseType: 'stream' });

    for await (const chunk of stream) {
      const data = JSON.parse(chunk.data);
      const content = data.choices[0]?.delta?.content || '';
      fullContent += content;

      if (onChunk) {
        onChunk({
          content,
          finishReason: data.choices[0]?.finish_reason
            ? this.mapFinishReason(data.choices[0].finish_reason)
            : undefined
        });
      }
    }

    return {
      content: fullContent,
      usage: {
        promptTokens: 0, // Calculé séparément
        completionTokens: totalTokens,
        totalTokens
      },
      model: params?.model || this.config.defaultModel,
      provider: this.name,
      latencyMs: Date.now() - startTime,
      finishReason: 'stop'
    };
  }

  async embed(texts: string[]): Promise<IEmbedding[]> {
    const response = await this.client.post('/embeddings', {
      model: 'kimi-embedding-v1',
      input: texts
    });

    return response.data.data.map((item: any, index: number) => ({
      vector: item.embedding,
      model: 'kimi-embedding-v1',
      dimensions: item.embedding.length
    }));
  }

  async healthCheck(): Promise<IProviderHealth> {
    const startTime = Date.now();
    try {
      await this.client.get('/models');
      return {
        status: 'healthy',
        latencyMs: Date.now() - startTime,
        lastChecked: new Date(),
        errorRate: 0
      };
    } catch (error) {
      return {
        status: 'down',
        latencyMs: Date.now() - startTime,
        lastChecked: new Date(),
        errorRate: 1
      };
    }
  }

  getCostEstimate(promptTokens: number, model?: string): ICostEstimate {
    const m = model || this.config.defaultModel;
    // Tarification Moonshot AI (à adapter selon grille réelle)
    const rates: Record<string, { input: number; output: number }> = {
      'kimi-moonshot-v1-8k': { input: 0.00001, output: 0.00002 },
      'kimi-moonshot-v1-32k': { input: 0.00002, output: 0.00004 },
      'kimi-moonshot-v1-128k': { input: 0.00004, output: 0.00008 }
    };
    const rate = rates[m] || rates['kimi-moonshot-v1-8k'];
    const estimatedCost = promptTokens * rate.input + (promptTokens * 0.5) * rate.output;

    return {
      provider: this.name,
      model: m,
      estimatedCostUsd: estimatedCost,
      currency: 'USD'
    };
  }

  async dispose(): Promise<void> {
    this.client = null;
  }

  // ─── Helpers privés ───

  private buildMessages(prompt: string, context?: string[]): any[] {
    const messages: any[] = [];
    if (context) {
      messages.push(...context.map(c => ({ role: 'system', content: c })));
    }
    messages.push({ role: 'user', content: prompt });
    return messages;
  }

  private mapFinishReason(reason: string): IAIResponse['finishReason'] {
    const mapping: Record<string, IAIResponse['finishReason']> = {
      'stop': 'stop',
      'length': 'length',
      'content_filter': 'content_filter',
      'tool_calls': 'stop'
    };
    return mapping[reason] || 'error';
  }
}

// ============================================================================
// IMPLEMENTATION : ClaudeAdapter (Anthropic)
// ============================================================================

export class ClaudeAdapter implements IAIProvider {
  readonly name = 'claude';
  readonly version = '1.0.0';
  readonly supportedModels = [
    'claude-3-5-sonnet-20241022',
    'claude-3-opus-20240229',
    'claude-3-sonnet-20240229',
    'claude-3-haiku-20240307'
  ];

  private config!: IProviderConfig;
  private client: any;

  async initialize(config: IProviderConfig): Promise<void> {
    this.config = config;
    this.client = new HttpClient({
      baseURL: config.baseUrl || 'https://api.anthropic.com/v1',
      headers: {
        'x-api-key': config.apiKey,
        'anthropic-version': '2023-06-01'
      },
      timeout: config.timeoutMs
    });
  }

  async generate(
    prompt: string,
    context?: string[],
    params?: IModelParams
  ): Promise<IAIResponse> {
    const startTime = Date.now();

    const response = await this.client.post('/messages', {
      model: params?.model || this.config.defaultModel,
      max_tokens: params?.maxTokens || 4096,
      temperature: params?.temperature ?? 0.7,
      system: context?.join('\n'),
      messages: [{ role: 'user', content: prompt }],
      tools: params?.tools?.map(t => ({
        name: t.name,
        description: t.description,
        input_schema: t.parameters
      }))
    });

    const data = response.data;

    return {
      content: data.content[0]?.text || '',
      usage: {
        promptTokens: data.usage.input_tokens,
        completionTokens: data.usage.output_tokens,
        totalTokens: data.usage.input_tokens + data.usage.output_tokens
      },
      model: data.model,
      provider: this.name,
      latencyMs: Date.now() - startTime,
      finishReason: this.mapFinishReason(data.stop_reason),
      metadata: { anthropicSpecific: data }
    };
  }

  async stream(
    prompt: string,
    context?: string[],
    params?: IModelParams,
    onChunk?: (chunk: IAIStreamChunk) => void
  ): Promise<IAIResponse> {
    // Implémentation similaire à KimiAdapter avec format SSE Anthropic
    throw new Error('Streaming Claude : implémenter avec SSE');
  }

  async embed(texts: string[]): Promise<IEmbedding[]> {
    // Anthropic ne fournit pas d'API d'embeddings native
    // Fallback vers un provider d'embeddings dédié
    throw new Error('Claude ne supporte pas les embeddings natifs. Utiliser OpenAIAdapter.embed()');
  }

  async healthCheck(): Promise<IProviderHealth> {
    const startTime = Date.now();
    try {
      await this.client.get('/models');
      return {
        status: 'healthy',
        latencyMs: Date.now() - startTime,
        lastChecked: new Date(),
        errorRate: 0
      };
    } catch {
      return {
        status: 'down',
        latencyMs: Date.now() - startTime,
        lastChecked: new Date(),
        errorRate: 1
      };
    }
  }

  getCostEstimate(promptTokens: number, model?: string): ICostEstimate {
    const m = model || this.config.defaultModel;
    const rates: Record<string, { input: number; output: number }> = {
      'claude-3-5-sonnet-20241022': { input: 0.000003, output: 0.000015 },
      'claude-3-opus-20240229': { input: 0.000015, output: 0.000075 },
      'claude-3-haiku-20240307': { input: 0.00000025, output: 0.00000125 }
    };
    const rate = rates[m] || rates['claude-3-5-sonnet-20241022'];
    const estimatedCost = promptTokens * rate.input + (promptTokens * 0.5) * rate.output;

    return {
      provider: this.name,
      model: m,
      estimatedCostUsd: estimatedCost,
      currency: 'USD'
    };
  }

  async dispose(): Promise<void> {
    this.client = null;
  }

  private mapFinishReason(reason: string): IAIResponse['finishReason'] {
    const mapping: Record<string, IAIResponse['finishReason']> = {
      'end_turn': 'stop',
      'max_tokens': 'length',
      'stop_sequence': 'stop',
      'tool_use': 'stop'
    };
    return mapping[reason] || 'error';
  }
}

// ============================================================================
// ROUTER INTELLIGENT — ModelRouter
// ============================================================================

export type RoutingStrategy = 
  | 'costOptimized'      // Moins cher
  | 'qualityOptimized'   // Meilleur modèle
  | 'latencyOptimized'   // Plus rapide
  | 'fallbackChain'      // Primaire → Secondaire → Local
  | 'roundRobin';        // Répartition équitable

export interface IRoutingDecision {
  provider: string;
  model: string;
  reason: string;
  estimatedCost: number;
  estimatedLatency: number;
}

export class ModelRouter {
  private providers: Map<string, IAIProvider> = new Map();
  private healthCache: Map<string, IProviderHealth> = new Map();
  private metrics: Map<string, { latency: number[]; errors: number }> = new Map();

  registerProvider(provider: IAIProvider): void {
    this.providers.set(provider.name, provider);
    this.metrics.set(provider.name, { latency: [], errors: 0 });
  }

  async route(
    prompt: string,
    strategy: RoutingStrategy = 'fallbackChain',
    context?: string[],
    params?: IModelParams
  ): Promise<IAIResponse> {
    const decision = await this.selectProvider(strategy, prompt);
    const provider = this.providers.get(decision.provider);

    if (!provider) {
      throw new Error(`Provider ${decision.provider} not found`);
    }

    const startTime = Date.now();
    try {
      const response = await provider.generate(prompt, context, {
        ...params,
        model: decision.model
      });

      // Mise à jour des métriques
      const metrics = this.metrics.get(decision.provider)!;
      metrics.latency.push(Date.now() - startTime);
      if (metrics.latency.length > 100) metrics.latency.shift();

      return response;
    } catch (error) {
      const metrics = this.metrics.get(decision.provider)!;
      metrics.errors++;

      if (strategy === 'fallbackChain') {
        return this.fallback(prompt, decision.provider, context, params);
      }
      throw error;
    }
  }

  private async selectProvider(
    strategy: RoutingStrategy,
    prompt: string
  ): Promise<IRoutingDecision> {
    const availableProviders = Array.from(this.providers.values());

    switch (strategy) {
      case 'costOptimized':
        return this.selectByCost(availableProviders, prompt);
      case 'qualityOptimized':
        return this.selectByQuality(availableProviders);
      case 'latencyOptimized':
        return this.selectByLatency(availableProviders);
      case 'fallbackChain':
        return this.selectPrimary(availableProviders);
      case 'roundRobin':
        return this.selectRoundRobin(availableProviders);
      default:
        return this.selectPrimary(availableProviders);
    }
  }

  private async selectByCost(
    providers: IAIProvider[],
    prompt: string
  ): Promise<IRoutingDecision> {
    const estimates = providers.map(p => ({
      provider: p.name,
      estimate: p.getCostEstimate(prompt.length * 0.25, p.supportedModels[0])
    }));

    const cheapest = estimates.reduce((min, curr) => 
      curr.estimate.estimatedCostUsd < min.estimate.estimatedCostUsd ? curr : min
    );

    return {
      provider: cheapest.provider,
      model: cheapest.estimate.model,
      reason: 'costOptimized',
      estimatedCost: cheapest.estimate.estimatedCostUsd,
      estimatedLatency: 0
    };
  }

  private selectByQuality(providers: IAIProvider[]): IRoutingDecision {
    // Priorité : Claude Opus > Kimi k1.5 > Claude Sonnet > GPT-4o > etc.
    const qualityRanking = ['claude', 'kimi', 'openai'];
    for (const name of qualityRanking) {
      const provider = providers.find(p => p.name === name);
      if (provider) {
        return {
          provider: provider.name,
          model: provider.supportedModels[0],
          reason: 'qualityOptimized',
          estimatedCost: 0,
          estimatedLatency: 0
        };
      }
    }
    throw new Error('No quality provider available');
  }

  private selectByLatency(providers: IAIProvider[]): IRoutingDecision {
    const sorted = providers.map(p => {
      const metrics = this.metrics.get(p.name)!;
      const avgLatency = metrics.latency.length > 0
        ? metrics.latency.reduce((a, b) => a + b, 0) / metrics.latency.length
        : Infinity;
      return { provider: p, avgLatency };
    }).sort((a, b) => a.avgLatency - b.avgLatency);

    return {
      provider: sorted[0].provider.name,
      model: sorted[0].provider.supportedModels[0],
      reason: 'latencyOptimized',
      estimatedCost: 0,
      estimatedLatency: sorted[0].avgLatency
    };
  }

  private selectPrimary(providers: IAIProvider[]): IRoutingDecision {
    // Par défaut : Kimi comme primaire (partenariat CVLN/Moonshot)
    const primary = providers.find(p => p.name === 'kimi') || providers[0];
    return {
      provider: primary.name,
      model: primary.supportedModels[0],
      reason: 'fallbackChain:primary',
      estimatedCost: 0,
      estimatedLatency: 0
    };
  }

  private selectRoundRobin(providers: IAIProvider[]): IRoutingDecision {
    // Implémentation simplifiée
    const idx = Math.floor(Math.random() * providers.length);
    return {
      provider: providers[idx].name,
      model: providers[idx].supportedModels[0],
      reason: 'roundRobin',
      estimatedCost: 0,
      estimatedLatency: 0
    };
  }

  private async fallback(
    prompt: string,
    failedProvider: string,
    context?: string[],
    params?: IModelParams
  ): Promise<IAIResponse> {
    const fallbackOrder = ['kimi', 'claude', 'openai', 'local'];
    const startIdx = fallbackOrder.indexOf(failedProvider) + 1;

    for (let i = startIdx; i < fallbackOrder.length; i++) {
      const provider = this.providers.get(fallbackOrder[i]);
      if (provider) {
        try {
          return await provider.generate(prompt, context, params);
        } catch {
          continue;
        }
      }
    }

    throw new Error('All providers failed in fallback chain');
  }

  async refreshHealth(): Promise<void> {
    for (const [name, provider] of this.providers) {
      const health = await provider.healthCheck();
      this.healthCache.set(name, health);
    }
  }
}

// ============================================================================
// USAGE EXEMPLE
// ============================================================================

/*
import { KimiAdapter, ClaudeAdapter, ModelRouter } from './provider-adapter';

// Initialisation
const kimi = new KimiAdapter();
await kimi.initialize({
  apiKey: process.env.KIMI_API_KEY!,
  defaultModel: 'kimi-moonshot-v1-128k',
  timeoutMs: 30000,
  retryPolicy: { maxRetries: 3, backoffMs: 1000 }
});

const claude = new ClaudeAdapter();
await claude.initialize({
  apiKey: process.env.ANTHROPIC_API_KEY!,
  defaultModel: 'claude-3-5-sonnet-20241022',
  timeoutMs: 30000,
  retryPolicy: { maxRetries: 2, backoffMs: 2000 }
});

// Router
const router = new ModelRouter();
router.registerProvider(kimi);
router.registerProvider(claude);

// Appel avec stratégie
const response = await router.route(
  'Analyser les KPIs du Q3 pour KORA',
  'costOptimized',  // Ou 'qualityOptimized', 'latencyOptimized', 'fallbackChain'
  ['Tu es l'agent Data Science AGT-060. Contexte : KORA Q3 2026.'],
  { temperature: 0.3, maxTokens: 2000 }
);

console.log(`Réponse via ${response.provider} / ${response.model}`);
console.log(`Coût estimé : ${response.usage.totalTokens} tokens`);
console.log(`Latence : ${response.latencyMs}ms`);
*/
