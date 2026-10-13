// Transaction orchestration — repository, event publisher, validator, and
// the orchestrator itself.
//
// Java mapping notes: Spring's @Service is not simulated — X has no DI
// container, so TransactionConfiguration (configuration.x) acts as the
// composition root and wires collaborators explicitly.

import pipeline.{ProcessingStage, ProcessingContext, TransactionCommand, TransactionResult}
import events.DomainEvent

export interface TransactionRepository {
    void save(TransactionResult result);
    boolean exists(string transactionId);
}

export class InMemoryTransactionRepository implements TransactionRepository {
    private HashMap store = new HashMap();

    public void save(TransactionResult result) {
        this.store.set(result.transactionId(), result);
    }

    public boolean exists(string transactionId) {
        return this.store.has(transactionId);
    }
}

export interface ApplicationEventPublisher {
    void publish(DomainEvent event);
}

export class LoggingEventPublisher implements ApplicationEventPublisher {
    public void publish(DomainEvent event) {
        print(`  [publisher] {typeOf(event)}.{event.eventId()} at {event.occurredAt()}`);
    }
}

export interface TransactionRule {
    boolean approve(TransactionCommand command, ProcessingContext context);
    string description();
}

export interface TransactionValidator {
    boolean validate(TransactionCommand command, ProcessingContext context);
}

export class CompositeTransactionValidator implements TransactionValidator {
    private TransactionRule[] rules;

    public CompositeTransactionValidator(TransactionRule[] rules) {
        // Defensive copy, like List.copyOf in the Java original.
        this.rules = [...rules];
    }

    public boolean validate(TransactionCommand command, ProcessingContext context) {
        for (TransactionRule rule of this.rules) {
            if (!rule.approve(command, context)) {
                print(`  [validator] rejected by rule: {rule.description()}`);
                return false;
            }
        }
        return true;
    }
}

// Java: @Service TransactionOrchestrator — constructor + repository()
// accessor, faithfully; the stage loop is exercised from main.x because the
// Java skeleton does not define one.
export class TransactionOrchestrator {
    private ProcessingStage<any, any>[] stages;
    // Java's private field is also named `repository`, but X forbids a field
    // and method sharing a name — the field is `store`, the accessor keeps
    // the Java name `repository()`.
    private TransactionRepository store;
    private ApplicationEventPublisher eventPublisher;

    public TransactionOrchestrator(
            ProcessingStage<any, any>[] stages,
            TransactionRepository repository,
            ApplicationEventPublisher eventPublisher) {
        // List.copyOf semantics: the orchestrator does not alias the caller's
        // list.
        this.stages = [...stages];
        this.store = repository;
        this.eventPublisher = eventPublisher;
    }

    public TransactionRepository repository() {
        return this.store;
    }

    public ApplicationEventPublisher publisher() {
        return this.eventPublisher;
    }

    public integer stageCount() {
        return this.stages.length;
    }
}
