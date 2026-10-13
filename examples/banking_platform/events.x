// Domain events — interfaces and value types.
//
// Java mapping notes:
//   UUID                  -> string (no native UUID type in X)
//   Instant               -> integer (epoch millis)
//   CompletionStage<T>    -> an awaitable returned by a top-level `async`
//                            function; X interfaces cannot declare async
//                            methods, so `handle` is typed `any` and callers
//                            `await` the result (see main.x)
//   Class<E> eventType()  -> string event type name (no reflection in X)
//   <E extends DomainEvent> bounds are not supported by X's grammar —
//                            the parameters are plain <E, C> hints.

export interface DomainEvent {
    string eventId();
    integer occurredAt();
}

export interface EventContext {
    string tenantId();
    string correlationId();
    SecurityContext securityContext();
}

// Generic event handler. X accepts interface type parameters but does not
// enforce bounds, so E/C are documentation-grade hints, as in the Java
// original's usage sites.
export interface EventHandler<E, C> {
    string eventType();
    any handle(E event, C context);
}

export final class SecurityContext {
    private string principal;
    private Set<string> scopes;

    public SecurityContext(string principal, Set<string> scopes) {
        this.principal = principal;
        this.scopes = scopes;
    }

    public string getPrincipal() { return this.principal; }
    public Set<string> getScopes() { return this.scopes; }
}

// Java: public record CorrelationId(String value) {}
// X forbids a field and method sharing a name, so the backing fields are
// underscore-prefixed; the record accessor keeps its Java name.
export final class CorrelationId {
    private final string _value;

    public CorrelationId(string value) {
        this._value = value;
    }

    public string value() { return this._value; }
}

// X enums cannot nest inside classes, so this is module-level.
export enum HandlerResultStatus { SUCCESS, RETRYABLE_FAILURE, PERMANENT_FAILURE }

// Java: public record HandlerResult(Status, List<DomainEvent>, Map<String, Object>)
// Backing fields are underscore-prefixed — X forbids field/method name clashes.
export final class HandlerResult {
    private final HandlerResultStatus _status;
    private final List<DomainEvent> _emittedEvents;
    private final HashMap _metadata;

    public HandlerResult(
            HandlerResultStatus status,
            List<DomainEvent> emittedEvents,
            HashMap metadata) {
        this._status = status;
        this._emittedEvents = emittedEvents;
        this._metadata = metadata;
    }

    public HandlerResultStatus status() { return this._status; }
    public List<DomainEvent> emittedEvents() { return this._emittedEvents; }
    public HashMap metadata() { return this._metadata; }
}

// A concrete event used by the pipeline demo.
export class PaymentReceived implements DomainEvent {
    private final string id;
    private final string tenant;
    private final integer amountCents;
    private final integer receivedAt;

    public PaymentReceived(string id, string tenant, integer amountCents, integer receivedAt) {
        this.id = id;
        this.tenant = tenant;
        this.amountCents = amountCents;
        this.receivedAt = receivedAt;
    }

    public string eventId() { return this.id; }
    public integer occurredAt() { return this.receivedAt; }
    public string getTenant() { return this.tenant; }
    public integer getAmountCents() { return this.amountCents; }
}

// A concrete handler showing the EventHandler<E, C> pattern.
export class PaymentReceivedHandler implements EventHandler<PaymentReceived, EventContext> {
    public string eventType() {
        return "PaymentReceived";
    }

    public any handle(PaymentReceived event, EventContext context) {
        return finalizePayment(event, context);
    }
}

async any function finalizePayment(PaymentReceived event, EventContext context) {
    // Simulated async work — the CompletionStage-equivalent in X.
    await sleep(1);
    let emitted = new List();
    let metadata = new HashMap();
    metadata.set("tenant", event.getTenant());
    metadata.set("processedBy", context.correlationId());
    print(`  [handler] PaymentReceived {event.eventId()} for {event.getTenant()} = {event.getAmountCents()} cents`);
    return new HandlerResult(HandlerResultStatus.SUCCESS, emitted, metadata);
}

// A concrete EventContext used by the demo.
export class DefaultEventContext implements EventContext {
    private string tenant;
    private string correlation;
    private SecurityContext security;

    public DefaultEventContext(string tenant, string correlation, SecurityContext security) {
        this.tenant = tenant;
        this.correlation = correlation;
        this.security = security;
    }

    public string tenantId() { return this.tenant; }
    public string correlationId() { return this.correlation; }
    public SecurityContext securityContext() { return this.security; }
}
