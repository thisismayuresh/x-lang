// getActiveSubscription — traverses a static list and maps each item into a
// single giant typed map (nested objects inline), the JS
// `.map(subscriptionData => ({ ... }))` shape.
//
// Run:  x run examples/subscription_demo.x

export class ActiveSubscription {
    public string email;
    public string plan;
    public string billingCycle;
    public string status;
    public integer seats;
    public integer storageGb;
    public integer discountPercent;
    public string supportTier;
    public boolean chats;
    public boolean videoCalls;
    public boolean whiteboards;
    public boolean guestLinks;
    public string messageHistory;
    public integer maxUploads;
    public integer maxFileMb;
    public integer maxChannels;
    public integer maxApiCallsPerMin;
    public boolean extraStorage;
    public boolean prioritySupport;
    public boolean compliancePack;

    public ActiveSubscription(
            string email, string plan, string billingCycle, string status,
            integer seats, integer storageGb, integer discountPercent,
            string supportTier, boolean chats, boolean videoCalls,
            boolean whiteboards, boolean guestLinks, string messageHistory,
            integer maxUploads, integer maxFileMb, integer maxChannels,
            integer maxApiCallsPerMin, boolean extraStorage,
            boolean prioritySupport, boolean compliancePack) {
        this.email = email;
        this.plan = plan;
        this.billingCycle = billingCycle;
        this.status = status;
        this.seats = seats;
        this.storageGb = storageGb;
        this.discountPercent = discountPercent;
        this.supportTier = supportTier;
        this.chats = chats;
        this.videoCalls = videoCalls;
        this.whiteboards = whiteboards;
        this.guestLinks = guestLinks;
        this.messageHistory = messageHistory;
        this.maxUploads = maxUploads;
        this.maxFileMb = maxFileMb;
        this.maxChannels = maxChannels;
        this.maxApiCallsPerMin = maxApiCallsPerMin;
        this.extraStorage = extraStorage;
        this.prioritySupport = prioritySupport;
        this.compliancePack = compliancePack;
    }
}

// The static list that gets traversed — no function call needed.
export const List activeSubscriptionData = new List([
    new ActiveSubscription(
        "ada@example.com", "Business", "annual", "active",
        25, 500, 15, "priority",
        true, true, false, true, "unlimited",
        10, 250, 50, 1000,
        true, true, false
    ),
    new ActiveSubscription(
        "grace@example.com", "Pro", "monthly", "active",
        5, 100, 0, "standard",
        true, false, false, true, "90d",
        5, 100, 10, 250,
        false, false, false
    )
]);

// Traverse the static list; each item maps into one giant typed map with the
// nested groups inline.
export function getActiveSubscription() {
    return activeSubscriptionData.map((ActiveSubscription subscriptionData) => {
        return {
            email: subscriptionData.email,
            plan: subscriptionData.plan,
            billingCycle: subscriptionData.billingCycle,
            status: subscriptionData.status,
            seats: subscriptionData.seats,
            storageGb: subscriptionData.storageGb,
            discountPercent: subscriptionData.discountPercent,
            supportTier: subscriptionData.supportTier,
            features: {
                chats: subscriptionData.chats,
                videoCalls: subscriptionData.videoCalls,
                whiteboards: subscriptionData.whiteboards,
                guestLinks: subscriptionData.guestLinks,
                messageHistory: subscriptionData.messageHistory
            },
            limits: {
                maxUploads: subscriptionData.maxUploads,
                maxFileMb: subscriptionData.maxFileMb,
                maxChannels: subscriptionData.maxChannels,
                maxApiCallsPerMin: subscriptionData.maxApiCallsPerMin
            },
            addons: {
                extraStorage: subscriptionData.extraStorage,
                prioritySupport: subscriptionData.prioritySupport,
                compliancePack: subscriptionData.compliancePack
            }
        };
    });
}

any function main() {
    let result = getActiveSubscription();
    let Object<string, any> first = result[0];

   
}
