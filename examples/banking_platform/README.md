# Banking platform — Java → X translation

A faithful port of a Spring-flavoured Java codebase into idiomatic X,
split across six files. Run it with:

```sh
x run examples/banking_platform/main.x
```

## Files

| File | Java source material |
| --- | --- |
| `platform.x` | `BankingPlatform` + the deeply nested `PlatformConfig` hierarchy (security/database/messaging/transaction config), plus `Duration`, enums (`Permission`, `Effect`, `LogicalOperator`, `RoutingStrategy`), `RetryConfig`, `Condition` |
| `events.x` | `DomainEvent`, `EventContext`, `EventHandler<E, C>`, `CorrelationId`, `HandlerResult`, plus a concrete `PaymentReceived` event + handler |
| `pipeline.x` | `ProcessingStage<I, O>`, `TransactionCommand`, `TransactionResult`, `ProcessingContext`, `TenantContext`, `ExecutionMetadata` |
| `orchestrator.x` | `TransactionRepository`, `ApplicationEventPublisher`, `TransactionRule`, `TransactionValidator`, `CompositeTransactionValidator`, `TransactionOrchestrator` |
| `configuration.x` | Spring `@Configuration` class — static factory methods act as the composition root (X has no DI container) |
| `main.x` | Wires everything: builds a full `PlatformConfig`, performs the deep getter-chain access, runs a transaction through a stage, and awaits an async event handler |

## Notable Java → X adaptations

- **`UUID` → `string`**, **`Instant` → `integer`** (epoch millis),
  **`URI` → `string`** — X has none of these types.
- **`Duration`** — modelled as a small final class with
  `ofSeconds/ofMinutes/ofHours/ofDays/ofMillis` factories (millisecond field).
- **`Map<K,V>` → `HashMap`** — plain X `object<K,V>` literals have no
  `.get()/.set()` methods; `HashMap` instances do, so deep chains like
  `getKeys().get("primary")` work as in Java.
- **`Set<V>` → `Set`**, **`List<V>` → `List`** (LinkedList); generics are
  documentation-grade hints, as the README documents.
- **`List.copyOf(stages)`** → spread copy `[...stages]`.
- **`Class<E> eventType()`** → `string eventType()` returning the type's
  name — X has no reflection.
- **`CompletionStage<T>`** → X has no `Promise` type and interfaces cannot
  declare `async` methods, so async results are `any`-typed awaitables
  returned from top-level `async` functions; callers `await` the result
  (see `PaymentReceivedHandler` and `AuthorizeStage` in `main.x`).
- **Records** (`CorrelationId`, `HandlerResult`, `ProcessingContext`) →
  classes with constructor + accessor methods.
- **Generic bounds** (`E extends DomainEvent`) are not supported by X's
  grammar — parameters stay as plain `<E, C>` hints.
- **Nested enums** are not accessible at runtime (`Outer.Status.OK` fails),
  so `HandlerResult.Status` became module-level `HandlerResultStatus`.
- **Field/method name clashes** are forbidden in X: Java's record-style
  accessors (`status()` method + `status` field) use underscore-prefixed
  backing fields (`_status`); `TransactionOrchestrator.repository()` keeps
  the Java accessor name over the private field name.
- **No string interpolation in `"..."`** — X interpolates only in backtick
  strings (`` `x + 1 = {x + 1}` ``).
- **No numeric separators** — `1_000_000` is written `1000000`.
- **`as` casts do not exist** — X dispatches dynamically; upcasts are
  implicit.
- **Spring annotations** (`@Service`, `@Bean`) are not simulated; the
  `TransactionConfiguration` factory methods play the wiring role.
