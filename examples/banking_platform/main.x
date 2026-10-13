// Banking platform demo — wires the Java-equivalent hierarchy, performs the
// deep getter-chain access, and exercises the generic pipeline + event
// handler.
//
// Run:  x run examples/banking_platform/main.x

import events.{
    DefaultEventContext,
    HandlerResult,
    PaymentReceived,
    PaymentReceivedHandler,
    SecurityContext
}
import orchestrator.{
    ApplicationEventPublisher,
    InMemoryTransactionRepository,
    LoggingEventPublisher,
    TransactionOrchestrator,
    TransactionRepository,
    TransactionRule,
    TransactionValidator
}
import pipeline.{
    ExecutionMetadata,
    ProcessingContext,
    ProcessingStage,
    TenantContext,
    TransactionCommand,
    TransactionResult
}
import configuration.TransactionConfiguration
import platform.{
    BankingPlatform,
    Condition,
    Duration,
    Effect,
    LogicalOperator,
    Permission,
    RetryConfig,
    RoutingStrategy
}

// ---- demo pipeline stage ------------------------------------------------

class AuthorizeCommand implements TransactionCommand {
    private string id;
    private integer amountCents;

    public AuthorizeCommand(string id, integer amountCents) {
        this.id = id;
        this.amountCents = amountCents;
    }

    public string transactionId() { return this.id; }
    public integer getAmountCents() { return this.amountCents; }
}

class AuthorizeResult implements TransactionResult {
    private string id;
    private boolean approved;

    public AuthorizeResult(string id, boolean approved) {
        this.id = id;
        this.approved = approved;
    }

    public string transactionId() { return this.id; }
    public boolean isApproved() { return this.approved; }
}

class AuthorizeStage
        implements ProcessingStage<AuthorizeCommand, AuthorizeResult> {

    public any execute(AuthorizeCommand input, ProcessingContext context) {
        return runAuthorize(input, context);
    }
}

async any function runAuthorize(AuthorizeCommand input, ProcessingContext context) {
    // Stage body — the awaitable CompletionStage equivalent.
    await sleep(1);
    let approved = input.getAmountCents() <= 1000000;
    print(`  [stage] authorize {input.transactionId()} -> {approved}`);
    return new AuthorizeResult(input.transactionId(), approved);
}

class AmountRule implements TransactionRule {
    private integer limitCents;

    public AmountRule(integer limitCents) {
        this.limitCents = limitCents;
    }

    public boolean approve(TransactionCommand command, ProcessingContext context) {
        // X dispatches dynamically — no cast needed.
        return command.getAmountCents() <= this.limitCents;
    }

    public string description() {
        return `amount <= {this.limitCents} cents`;
    }
}

// ---- constructor-overload DI --------------------------------------------
// Mirrors the classic Java shape:
//
//   class Foo {
//       Foo(Bar bar)           { bar.callMethod(); }   // interface dep
//       Foo(SomeClass some)    { ... }                 // concrete dep
//   }
//
// X dispatches overloaded constructors by argument type, so the same class
// can be dependency-injected with either an interface or a concrete class.
// Here FraudScanner takes either an ApplicationEventPublisher (to raise
// alerts) or an InMemoryTransactionRepository (to look up prior txns).
class FraudScanner {
    private ApplicationEventPublisher alertPublisher;
    private TransactionRepository ledger;
    private string mode;

    // Overload 1 — inject an interface dependency and call a method on it.
    public FraudScanner(ApplicationEventPublisher alertPublisher) {
        this.alertPublisher = alertPublisher;
        this.ledger = new InMemoryTransactionRepository();
        this.mode = "publisher";
        // bar.callMethod() — use the injected interface immediately.
        this.alertPublisher.publish(new PaymentReceived("fraud-boot", "system", 0, 0));
    }

    // Overload 2 — inject a concrete dependency and use it.
    public FraudScanner(TransactionRepository ledger) {
        this.ledger = ledger;
        this.alertPublisher = new LoggingEventPublisher();
        this.mode = "ledger";
        this.alertPublisher.publish(new PaymentReceived("fraud-boot", "system", 0, 0));
    }

    public string scan(TransactionCommand command) {
        let prior = this.ledger.exists(command.transactionId());
        this.alertPublisher.publish(
            new PaymentReceived("fraud-scan", this.mode, command.getAmountCents(), 0)
        );
        if (prior) {
            return `DUPLICATE ({this.mode})`;
        }
        this.ledger.save(new AuthorizeResult(command.transactionId(), true));
        return `CLEAR ({this.mode})`;
    }
}

// ---- demo ---------------------------------------------------------------

async function main() {
    print("=== BankingPlatform: build the nested config ===");

    let primaryKeys = new HashMap();
    primaryKeys.set("primary", new BankingPlatform.PlatformConfig.SecurityConfig.JwtConfig.KeyConfig(
        "kid-1", "RS256", "https://keys.example.com/primary.jwks"
    ));
    primaryKeys.set("secondary", new BankingPlatform.PlatformConfig.SecurityConfig.JwtConfig.KeyConfig(
        "kid-2", "RS256", "https://keys.example.com/secondary.jwks"
    ));

    let audiences = new Set();
    audiences.add("banking-api");
    audiences.add("admin-portal");

    let jwt = new BankingPlatform.PlatformConfig.SecurityConfig.JwtConfig(
        "https://auth.example.com",
        Duration.ofMinutes(15),
        audiences,
        primaryKeys
    );

    let rolePermissions = new HashMap();
    let tellerPerms = new Set();
    tellerPerms.add(Permission.READ);
    tellerPerms.add(Permission.WRITE);
    rolePermissions.set("teller", tellerPerms);

    let policyConditions = new ConditionGroupDemo().build();
    let accessPolicy = new BankingPlatform.PlatformConfig.SecurityConfig.AuthorizationConfig.AccessPolicy(
        "/accounts/*",
        Effect.ALLOW,
        policyConditions
    );
    let policies = new List();
    policies.add(accessPolicy);

    let authorization = new BankingPlatform.PlatformConfig.SecurityConfig.AuthorizationConfig(
        rolePermissions,
        policies
    );

    let security = new BankingPlatform.PlatformConfig.SecurityConfig(jwt, authorization);

    let primaryPool = new BankingPlatform.PlatformConfig.DatabaseConfig.DataSourceConfig.PoolConfig(
        2, 10, Duration.ofSeconds(30),
        new BankingPlatform.PlatformConfig.DatabaseConfig.DataSourceConfig.PoolConfig.ValidationConfig(
            true, Duration.ofMinutes(1), "SELECT 1"
        )
    );
    let txConfig = new BankingPlatform.PlatformConfig.TransactionConfig(
        Duration.ofSeconds(30),
        new RetryConfig(3, Duration.ofSeconds(1)),
        new BankingPlatform.PlatformConfig.TransactionConfig.IdempotencyConfig(
            Duration.ofHours(24), "Idempotency-Key", true
        )
    );
    let dataSources = new HashMap();
    dataSources.set("primary", new BankingPlatform.PlatformConfig.DatabaseConfig.DataSourceConfig(
        "jdbc:postgresql://db.example.com:5432/ledger", primaryPool, txConfig
    ));
    let tenantRoutes = new HashMap();
    tenantRoutes.set("tenant-a", "primary");
    let database = new BankingPlatform.PlatformConfig.DatabaseConfig(
        dataSources,
        new BankingPlatform.PlatformConfig.DatabaseConfig.RoutingConfig(
            "primary", tenantRoutes, RoutingStrategy.TENANT_AFFINITY
        )
    );

    let deadLetter = new BankingPlatform.PlatformConfig.MessagingConfig.TopicConfig.ConsumerConfig.DeadLetterConfig(
        "payments.dlq", 5, Duration.ofDays(7)
    );
    let consumer = new BankingPlatform.PlatformConfig.MessagingConfig.TopicConfig.ConsumerConfig(
        4, Duration.ofMillis(500), deadLetter
    );
    let serialization = new BankingPlatform.PlatformConfig.MessagingConfig.TopicConfig.SerializationConfig(
        "StringSerializer", "JsonSerializer", { v1: "1", v2: "2" }
    );
    let topics = new HashMap();
    topics.set("payments", new BankingPlatform.PlatformConfig.MessagingConfig.TopicConfig(
        "payments.created", serialization, consumer
    ));
    let messaging = new BankingPlatform.PlatformConfig.MessagingConfig(
        topics,
        new RetryConfig(3, Duration.ofSeconds(2))
    );

    let config = new BankingPlatform.PlatformConfig(
        security, database, messaging, txConfig
    );
    let platform = new BankingPlatform(config);

    print("=== Deep access (the Java getter chain) ===");
    // Java:
    //   config.getSecurity().getJwt().getKeys().get("primary").getAlgorithm();
    let algorithm = platform.getConfig()
        .getSecurity()
        .getJwt()
        .getKeys()
        .get("primary")
        .getAlgorithm();
    print(`primary key algorithm: {algorithm}`);

    let route = platform.getConfig()
        .getDatabase()
        .getRouting()
        .getTenantRoutes()
        .get("tenant-a");
    print(`tenant-a routes to: {route}`);

    let dlqTopic = platform.getConfig()
        .getMessaging()
        .getTopics()
        .get("payments")
        .getConsumer()
        .getDeadLetter()
        .getTopic();
    print(`payments dead-letter topic: {dlqTopic}`);

    print("=== Wire the orchestrator (TransactionConfiguration) ===");
    let stages = [new AuthorizeStage()];
    let repository: TransactionRepository = new InMemoryTransactionRepository();
    let publisher: ApplicationEventPublisher = new LoggingEventPublisher();

    let orchestrator: TransactionOrchestrator =
        TransactionConfiguration.transactionOrchestrator(stages, repository, publisher);

    let rules = [new AmountRule(5000000)];
    let validator: TransactionValidator = TransactionConfiguration.transactionValidator(rules);

    print(`orchestrator stages: {orchestrator.stageCount()}`);
    print(`repository ready: {orchestrator.repository() != null}`);

    print("=== Run a transaction through a stage ===");
    let tenant = new TenantContext("tenant-a", "eu-west-1");
    let emptyScopes = new Set();
    let secCtx = new SecurityContext("alice@example.com", emptyScopes);
    let meta = new ExecutionMetadata("corr-001", 0);
    let context = new ProcessingContext(tenant, secCtx, meta);

    let command = new AuthorizeCommand("tx-1001", 250000);
    let approved = validator.validate(command, context);
    if (approved) {
        let result = await new AuthorizeStage().execute(command, context);
        repository.save(result);
        print(`saved: {result.transactionId()} approved={result.isApproved()}`);
        let known = repository.exists("tx-1001");
        print(`repository knows tx-1001: {known}`);
    }

    print("=== Async event handler (EventHandler<E, C>) ===");
    let handler = new PaymentReceivedHandler();
    let eventContext = new DefaultEventContext(
        "tenant-a", "corr-002", secCtx
    );
    let event = new PaymentReceived("evt-1", "tenant-a", 250000, 1726000000000);
    print(`handling {handler.eventType()} as {typeOf(event)}...`);
    let handlerResult = await handler.handle(event, eventContext);
    print(`handler status: {handlerResult.status()}`);
    let metaTenant = handlerResult.metadata().get("tenant");
    print(`handler metadata tenant: {metaTenant}`);

    print("=== Constructor-overload DI (FraudScanner) ===");
    // Overload 1: inject the ApplicationEventPublisher interface.
    let scannerByPublisher = new FraudScanner(publisher);
    print(`scan 1: {scannerByPublisher.scan(command)}`);
    // Same command again — the ledger it was handed already knows it.
    print(`scan 2 (dup): {scannerByPublisher.scan(command)}`);

    // Overload 2: inject a concrete TransactionRepository instead.
    let scannerByLedger = new FraudScanner(new InMemoryTransactionRepository());
    print(`scan 3 (fresh ledger): {scannerByLedger.scan(command)}`);

    print("=== done ===");
}

// Small helper building the nested ConditionGroup (avoids an even longer
// main body).
class ConditionGroupDemo {
    public BankingPlatform.PlatformConfig.SecurityConfig.AuthorizationConfig.AccessPolicy.ConditionGroup build() {
        let inner = new List();
        inner.add(new Condition("country", "==", "DE"));

        let nested = new List();
        nested.add(new BankingPlatform.PlatformConfig.SecurityConfig.AuthorizationConfig.AccessPolicy.ConditionGroup(
            LogicalOperator.AND, inner, new List()
        ));

        let top = new List();
        top.add(new Condition("role", "==", "teller"));

        return new BankingPlatform.PlatformConfig.SecurityConfig.AuthorizationConfig.AccessPolicy.ConditionGroup(
            LogicalOperator.AND, top, nested
        );
    }
}
