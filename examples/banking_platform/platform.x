// Banking platform — configuration object hierarchy.
//
// Faithful port of the Java BankingPlatform/PlatformConfig tree: private
// fields, Java-style getters, deeply nested static-style config classes.
// Java-only types are modelled honestly:
//   Duration -> the Duration class below (millisecond-based)
//   URI      -> string
//   Map<K,V> -> HashMap (supports .get/.set like java.util.Map)
//   Set<V>   -> Set

export final class Duration {
  public final integer millis;

  public Duration(integer millis) {
    this.millis = millis;
  }

  public static Duration ofSeconds(integer seconds) {
    return new Duration(seconds * 1000);
  }

    public static Duration ofMinutes(integer minutes) {
        return new Duration(minutes * 60000);
    }

    public static Duration ofHours(integer hours) {
        return new Duration(hours * 3600000);
    }

    public static Duration ofDays(integer days) {
        return new Duration(days * 86400000);
    }

    public static Duration ofMillis(integer millis) {
        return new Duration(millis);
    }
}

export enum Permission {
  READ, WRITE, ADMIN
}
export enum Effect {
  ALLOW, DENY
}
export enum LogicalOperator {
  AND, OR
}
export enum RoutingStrategy {
  ROUND_ROBIN, LEAST_CONNECTION, TENANT_AFFINITY
}

export class BankingPlatform {
  private PlatformConfig config;

  public BankingPlatform(PlatformConfig config) {
    this.config = config;
  }

  public PlatformConfig getConfig() {
    return this.config;
  }

  public static class PlatformConfig {
    private SecurityConfig security;
    private DatabaseConfig database;
    private MessagingConfig messaging;
    private TransactionConfig transactions;

    public PlatformConfig(SecurityConfig security, DatabaseConfig database, MessagingConfig messaging, TransactionConfig transactions) {
      this.security = security;
      this.database = database;
      this.messaging = messaging;
      this.transactions = transactions;
    }

    public SecurityConfig getSecurity() {
      return this.security;
    }
    public DatabaseConfig getDatabase() {
      return this.database;
    }
    public MessagingConfig getMessaging() {
      return this.messaging;
    }
    public TransactionConfig getTransactions() {
      return this.transactions;
    }

    public static class SecurityConfig {
      private JwtConfig jwt;
      private AuthorizationConfig authorization;

      public SecurityConfig(JwtConfig jwt, AuthorizationConfig authorization) {
        this.jwt = jwt;
        this.authorization = authorization;
      }

      public JwtConfig getJwt() {
        return this.jwt;
      }
      public AuthorizationConfig getAuthorization() {
        return this.authorization;
      }

      public static class JwtConfig {
        private string issuer;
        private Duration expiration;
        private Set < string > audiences;
        private HashMap keys;

        public JwtConfig(string issuer, Duration expiration, Set < string > audiences, HashMap keys) {
          this.issuer = issuer;
          this.expiration = expiration;
          this.audiences = audiences;
          this.keys = keys;
        }

        public string getIssuer() {
          return this.issuer;
        }
        public Duration getExpiration() {
          return this.expiration;
        }
        public Set < string > getAudiences() {
          return this.audiences;
        }
        public HashMap getKeys() {
          return this.keys;
        }

        public static class KeyConfig {
          private string keyId;
          private string algorithm;
          private string keyLocation;

          public KeyConfig(string keyId, string algorithm, string keyLocation) {
            this.keyId = keyId;
            this.algorithm = algorithm;
            this.keyLocation = keyLocation;
          }

          public string getKeyId() {
            return this.keyId;
          }
          public string getAlgorithm() {
            return this.algorithm;
          }
          public string getKeyLocation() {
            return this.keyLocation;
          }
        }
      }

      public static class AuthorizationConfig {
        private HashMap rolePermissions;
        private List < AccessPolicy > policies;

        public AuthorizationConfig(HashMap rolePermissions, List < AccessPolicy > policies) {
          this.rolePermissions = rolePermissions;
          this.policies = policies;
        }

        public HashMap getRolePermissions() {
          return this.rolePermissions;
        }
        public List < AccessPolicy > getPolicies() {
          return this.policies;
        }

        public static class AccessPolicy {
          private string resource;
          private Effect effect;
          private ConditionGroup conditions;

          public AccessPolicy(string resource, Effect effect, ConditionGroup conditions) {
            this.resource = resource;
            this.effect = effect;
            this.conditions = conditions;
          }

          public string getResource() {
            return this.resource;
          }
          public Effect getEffect() {
            return this.effect;
          }
          public ConditionGroup getConditions() {
            return this.conditions;
          }

          public static class ConditionGroup {
            private LogicalOperator operator;
            private List < Condition > conditions;
            private List < ConditionGroup > nestedGroups;

            public ConditionGroup(LogicalOperator operator, List < Condition > conditions, List < ConditionGroup > nestedGroups) {
              this.operator = operator;
              this.conditions = conditions;
              this.nestedGroups = nestedGroups;
            }

            public LogicalOperator getOperator() {
              return this.operator;
            }
            public List < Condition > getConditions() {
              return this.conditions;
            }
            public List < ConditionGroup > getNestedGroups() {
              return this.nestedGroups;
            }
          }
        }
      }
    }

    public static class DatabaseConfig {
      private HashMap dataSources;
      private RoutingConfig routing;

      public DatabaseConfig(HashMap dataSources, RoutingConfig routing) {
        this.dataSources = dataSources;
        this.routing = routing;
      }

      public HashMap getDataSources() {
        return this.dataSources;
      }
      public RoutingConfig getRouting() {
        return this.routing;
      }

      public static class DataSourceConfig {
        private string jdbcUrl;
        private PoolConfig pool;
        private TransactionConfig transaction;

        public DataSourceConfig(string jdbcUrl, PoolConfig pool, TransactionConfig transaction) {
          this.jdbcUrl = jdbcUrl;
          this.pool = pool;
          this.transaction = transaction;
        }

        public string getJdbcUrl() {
          return this.jdbcUrl;
        }
        public PoolConfig getPool() {
          return this.pool;
        }
        public TransactionConfig getTransaction() {
          return this.transaction;
        }

        public static class PoolConfig {
          private integer minSize;
          private integer maxSize;
          private Duration connectionTimeout;
          private ValidationConfig validation;

          public PoolConfig(integer minSize, integer maxSize, Duration connectionTimeout, ValidationConfig validation) {
            this.minSize = minSize;
            this.maxSize = maxSize;
            this.connectionTimeout = connectionTimeout;
            this.validation = validation;
          }

          public integer getMinSize() {
            return this.minSize;
          }
          public integer getMaxSize() {
            return this.maxSize;
          }
          public Duration getConnectionTimeout() {
            return this.connectionTimeout;
          }
          public ValidationConfig getValidation() {
            return this.validation;
          }

          public static class ValidationConfig {
            private boolean enabled;
            private Duration interval;
            private string validationQuery;

            public ValidationConfig(boolean enabled, Duration interval, string validationQuery) {
              this.enabled = enabled;
              this.interval = interval;
              this.validationQuery = validationQuery;
            }

            public boolean getEnabled() {
              return this.enabled;
            }
            public Duration getInterval() {
              return this.interval;
            }
            public string getValidationQuery() {
              return this.validationQuery;
            }
          }
        }
      }

      public static class RoutingConfig {
        private string defaultDataSource;
        private HashMap tenantRoutes;
        private RoutingStrategy strategy;

        public RoutingConfig(string defaultDataSource, HashMap tenantRoutes, RoutingStrategy strategy) {
          this.defaultDataSource = defaultDataSource;
          this.tenantRoutes = tenantRoutes;
          this.strategy = strategy;
        }

        public string getDefaultDataSource() {
          return this.defaultDataSource;
        }
        public HashMap getTenantRoutes() {
          return this.tenantRoutes;
        }
        public RoutingStrategy getStrategy() {
          return this.strategy;
        }
      }
    }

    public static class MessagingConfig {
      private HashMap topics;
      private RetryConfig retry;

      public MessagingConfig(HashMap topics, RetryConfig retry) {
        this.topics = topics;
        this.retry = retry;
      }

      public HashMap getTopics() {
        return this.topics;
      }
      public RetryConfig getRetry() {
        return this.retry;
      }

      public static class TopicConfig {
        private string topicName;
        private SerializationConfig serialization;
        private ConsumerConfig consumer;

        public TopicConfig(string topicName, SerializationConfig serialization, ConsumerConfig consumer) {
          this.topicName = topicName;
          this.serialization = serialization;
          this.consumer = consumer;
        }

        public string getTopicName() {
          return this.topicName;
        }
        public SerializationConfig getSerialization() {
          return this.serialization;
        }
        public ConsumerConfig getConsumer() {
          return this.consumer;
        }

        public static class SerializationConfig {
          private string keySerializer;
          private string valueSerializer;
          private HashMap schemaVersions;

          public SerializationConfig(string keySerializer, string valueSerializer, HashMap schemaVersions) {
            this.keySerializer = keySerializer;
            this.valueSerializer = valueSerializer;
            this.schemaVersions = schemaVersions;
          }

          public string getKeySerializer() {
            return this.keySerializer;
          }
          public string getValueSerializer() {
            return this.valueSerializer;
          }
          public HashMap getSchemaVersions() {
            return this.schemaVersions;
          }
        }

        public static class ConsumerConfig {
          private integer concurrency;
          private Duration pollTimeout;
          private DeadLetterConfig deadLetter;

          public ConsumerConfig(integer concurrency, Duration pollTimeout, DeadLetterConfig deadLetter) {
            this.concurrency = concurrency;
            this.pollTimeout = pollTimeout;
            this.deadLetter = deadLetter;
          }

          public integer getConcurrency() {
            return this.concurrency;
          }
          public Duration getPollTimeout() {
            return this.pollTimeout;
          }
          public DeadLetterConfig getDeadLetter() {
            return this.deadLetter;
          }

          public static class DeadLetterConfig {
            private string topic;
            private integer maxAttempts;
            private Duration retention;

            public DeadLetterConfig(string topic, integer maxAttempts, Duration retention) {
              this.topic = topic;
              this.maxAttempts = maxAttempts;
              this.retention = retention;
            }

            public string getTopic() {
              return this.topic;
            }
            public integer getMaxAttempts() {
              return this.maxAttempts;
            }
            public Duration getRetention() {
              return this.retention;
            }
          }
        }
      }
    }

    public static class TransactionConfig {
      private Duration timeout;
      private RetryConfig retry;
      private IdempotencyConfig idempotency;

      public TransactionConfig(Duration timeout, RetryConfig retry, IdempotencyConfig idempotency) {
        this.timeout = timeout;
        this.retry = retry;
        this.idempotency = idempotency;
      }

      public Duration getTimeout() {
        return this.timeout;
      }
      public RetryConfig getRetry() {
        return this.retry;
      }
      public IdempotencyConfig getIdempotency() {
        return this.idempotency;
      }

      public static class IdempotencyConfig {
        private Duration retention;
        private string keyHeader;
        private boolean rejectPayloadMismatch;

        public IdempotencyConfig(Duration retention, string keyHeader, boolean rejectPayloadMismatch) {
          this.retention = retention;
          this.keyHeader = keyHeader;
          this.rejectPayloadMismatch = rejectPayloadMismatch;
        }

        public Duration getRetention() {
          return this.retention;
        }
        public string getKeyHeader() {
          return this.keyHeader;
        }
        public boolean getRejectPayloadMismatch() {
          return this.rejectPayloadMismatch;
        }
      }
    }
  }
}

// Shared retry shape used by both TransactionConfig and MessagingConfig.
export class RetryConfig {
  private integer maxAttempts;
  private Duration backoff;

  public RetryConfig(integer maxAttempts, Duration backoff) {
    this.maxAttempts = maxAttempts;
    this.backoff = backoff;
  }

  public integer getMaxAttempts() {
    return this.maxAttempts;
  }
  public Duration getBackoff() {
    return this.backoff;
  }
}

// Authorization Condition — referenced by AccessPolicy.ConditionGroup.
export class Condition {
  private string claim;
  private string op;
  private string value;

  public Condition(string claim, string op, string value) {
    this.claim = claim;
    this.op = op;
    this.value = value;
  }

  public string getClaim() {
    return this.claim;
  }
  public string getOp() {
    return this.op;
  }
  public string getValue() {
    return this.value;
  }
}
