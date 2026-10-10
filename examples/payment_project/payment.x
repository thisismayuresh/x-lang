import gateway.Gateway

export enum PaymentStatus { PENDING, SETTLED, FAILED }

export class PaymentError extends Exception {
    public integer statusCode;

    public PaymentError(string message, integer statusCode) {
        super(message);
        this.statusCode = statusCode;
    }
}

export final class PaymentReceipt {
    public string id;
    public integer amount;

    public PaymentReceipt(string id, integer amount) {
        this.id = id;
        this.amount = amount;
    }
}

export abstract class AbstractPayment {
    static integer processed = 0;

    private string apiKey;
    private string mode;
    protected Gateway gateway;

    public AbstractPayment(Gateway gateway) {
        this.gateway = gateway;
        this.apiKey = System.process.Environment.has("PAYMENT_API_KEY")
            ? System.process.Environment.PAYMENT_API_KEY
            : "no-key";
        this.mode = System.process.Environment.has("GATEWAY_MODE")
            ? System.process.Environment.GATEWAY_MODE
            : "development";
    }

    public abstract integer makePayment(integer amount);

    public integer configurePaymentGateway() {
        print("configuring " + this.gateway.name() + " in " + this.mode);
        return this.gateway.name().length;
    }

    protected integer submit(integer amount) {
        if (amount < 0) {
            throw new PaymentError("amount must be positive", 422);
        }
        AbstractPayment.processed = AbstractPayment.processed + 1;
        return this.gateway.process(amount);
    }

    private string maskedKey() {
        return "key[..]" + this.mode;
    }

    public string describeConfig() {
        return this.maskedKey();
    }
}
