import gateway.{Gateway, StripeGateway, PaypalGateway}
import payment.{AbstractPayment, PaymentStatus, PaymentError, PaymentReceipt}

class CardPayment extends AbstractPayment {
    public CardPayment(Gateway gateway) {
        super(gateway);
    }

    public integer makePayment(integer amount) {
        return this.submit(amount) + 1;
    }
}

class CryptoPayment extends AbstractPayment {
    public CryptoPayment(Gateway gateway) {
        super(gateway);
    }

    public integer makePayment(integer amount) {
        return this.submit(amount) * 3;
    }

    public static CryptoPayment create(Gateway gateway) {
        return new CryptoPayment(gateway);
    }
}

function settle(PaymentReceipt receipt, PaymentStatus status) {
    switch (status) {
        case PaymentStatus.FAILED: {
            print("failed " + receipt.id);
        }
        case PaymentStatus.PENDING: {
            print("held " + receipt.id + " for review");
        }
        case PaymentStatus.SETTLED: {
            print("settled " + receipt.id + " for " + receipt.amount);
        }
    }
}

function main() {
    print("api key loaded: " + System.process.Environment.has("PAYMENT_API_KEY"));

    let Gateway stripe = new StripeGateway(
        System.process.Environment.has("PAYMENT_REGION")
            ? System.process.Environment.PAYMENT_REGION
            : "us"
    );
    let Gateway paypal = new PaypalGateway();

    let payments = [new CardPayment(stripe), CryptoPayment.create(paypal)];
    for (let payment of payments) {
        payment.configurePaymentGateway();
        print("charged " + payment.makePayment(100));
        print(payment.describeConfig());
    }
    print("processed " + AbstractPayment.processed);

    let PaymentReceipt receipt = new PaymentReceipt("rcpt-1", 130);
    settle(receipt, PaymentStatus.SETTLED);

    try {
        let CardPayment bad = new CardPayment(stripe);
        print(bad.makePayment(-5));
    } catch (PaymentError error) {
        print("declined: " + error.message + " (" + error.statusCode + ")");
    }
    print("processed " + AbstractPayment.processed);
}
