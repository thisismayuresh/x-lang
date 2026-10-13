// Generic transaction-processing pipeline.
//
// Java mapping notes:
//   UUID                          -> string
//   CompletionStage<O> execute()  -> `any` (awaitable from a top-level
//                                    async function; see events.x)
//   <I extends TransactionCommand> bounds unsupported — plain <I, O> hints
//   List<ProcessingStage<?,?>>    -> ProcessingStage<any, any>[] (no
//                                    wildcard syntax in X)

import events.SecurityContext

export interface TransactionCommand {
    string transactionId();
}

export interface TransactionResult {
    string transactionId();
}

// Generic stage: implement for a concrete command/result pair, e.g.
// class AuthorizeStage implements ProcessingStage<AuthorizeCommand, AuthorizeResult>
export interface ProcessingStage<I, O> {
    any execute(I input, ProcessingContext context);
}

export class TenantContext {
    private final string tenantId;
    private final string region;

    public TenantContext(string tenantId, string region) {
        this.tenantId = tenantId;
        this.region = region;
    }

    public string getTenantId() { return this.tenantId; }
    public string getRegion() { return this.region; }
}

export class ExecutionMetadata {
    private final string correlationId;
    private final integer startedAtMillis;

    public ExecutionMetadata(string correlationId, integer startedAtMillis) {
        this.correlationId = correlationId;
        this.startedAtMillis = startedAtMillis;
    }

    public string getCorrelationId() { return this.correlationId; }
    public integer getStartedAtMillis() { return this.startedAtMillis; }
}

// Java: public record ProcessingContext(TenantContext, SecurityContext, ExecutionMetadata)
export class ProcessingContext {
    private final TenantContext tenant;
    private final SecurityContext security;
    private final ExecutionMetadata metadata;

    public ProcessingContext(
            TenantContext tenant,
            SecurityContext security,
            ExecutionMetadata metadata) {
        this.tenant = tenant;
        this.security = security;
        this.metadata = metadata;
    }

    public TenantContext getTenant() { return this.tenant; }
    public SecurityContext getSecurity() { return this.security; }
    public ExecutionMetadata getMetadata() { return this.metadata; }
}
