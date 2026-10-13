// Spring @Configuration analogue — X has no DI container, so this class is
// the composition root: static factory methods (@Bean equivalents) that
// construct and wire the orchestrator and validator exactly like the Java
// TransactionConfiguration would through Spring.

import pipeline.ProcessingStage
import orchestrator.{
    TransactionOrchestrator,
    TransactionRepository,
    ApplicationEventPublisher,
    TransactionValidator,
    TransactionRule,
    CompositeTransactionValidator
}

export class TransactionConfiguration {

    // @Bean transactionOrchestrator(...)
    public static TransactionOrchestrator transactionOrchestrator(
            ProcessingStage<any, any>[] stages,
            TransactionRepository repository,
            ApplicationEventPublisher eventPublisher) {

        return new TransactionOrchestrator(
            stages,
            repository,
            eventPublisher
        );
    }

    // @Bean transactionValidator(...)
    public static TransactionValidator transactionValidator(
            TransactionRule[] rules) {

        return new CompositeTransactionValidator(rules);
    }
}
