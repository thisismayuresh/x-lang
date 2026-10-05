integer function maxProfit(integer[] prices) {
    if (prices.length < 2) {
        return 0;
    }

    let integer lowestPrice = prices[0];
    let integer bestProfit = 0;
    let integer profit = 0;

    for (let day = 1; day < prices.length; day++) {
        profit = prices[day] - lowestPrice;
        bestProfit = profit > bestProfit ? profit : bestProfit;
        lowestPrice = prices[day] < lowestPrice ? prices[day] : lowestPrice;
    }

    return bestProfit;
}

function main() {
    print("Best stock profit:", maxProfit([7, 1, 5, 3, 6, 4]));
}
