import SwiftUI
import SwiftData
import Charts

struct DashboardView: View {
    @Query(sort: \Transaction.date, order: .reverse) private var transactions: [Transaction]
    @Query(sort: \BudgetCategory.sortOrder) private var categories: [BudgetCategory]
    var onAdd: () -> Void

    @State private var appeared = false

    private var summary: MonthSummary {
        BudgetMath.summary(for: transactions)
    }

    private var recent: [Transaction] {
        Array(transactions.prefix(6))
    }

    private var breakdown: [(BudgetCategory, Double)] {
        BudgetMath.categoryBreakdown(transactions: transactions)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ScreenBackground()

                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 28) {
                        header
                        balanceHero
                        quickStats
                        if !breakdown.isEmpty {
                            spendingChart
                        }
                        recentSection
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 8)
                    .padding(.bottom, 36)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: onAdd) {
                        Image(systemName: "plus.circle.fill")
                            .font(.title2)
                            .symbolRenderingMode(.hierarchical)
                            .foregroundStyle(AppTheme.pine)
                    }
                    .accessibilityLabel("Add transaction")
                }
            }
            .onAppear {
                withAnimation(.spring(response: 0.7, dampingFraction: 0.86)) {
                    appeared = true
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Ledger")
                .font(.system(size: 38, weight: .bold, design: .rounded))
                .foregroundStyle(AppTheme.ink)
                .opacity(appeared ? 1 : 0)
                .offset(y: appeared ? 0 : 12)
            Text(Formatters.monthYear.string(from: .now))
                .font(.system(.subheadline, design: .rounded, weight: .medium))
                .foregroundStyle(AppTheme.inkMuted)
                .opacity(appeared ? 1 : 0)
        }
    }

    private var balanceHero: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Available this month")
                .font(.system(.subheadline, design: .rounded, weight: .medium))
                .foregroundStyle(.white.opacity(0.85))
            Text(Formatters.money(summary.balance))
                .font(.system(size: 44, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .contentTransition(.numericText())
            Text(summary.balance >= 0 ? "You're on track" : "Spending ahead of income")
                .font(.system(.caption, design: .rounded))
                .foregroundStyle(.white.opacity(0.8))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(24)
        .background(AppTheme.heroGradient)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: AppTheme.pine.opacity(0.25), radius: 24, y: 12)
        .scaleEffect(appeared ? 1 : 0.96)
        .opacity(appeared ? 1 : 0)
    }

    private var quickStats: some View {
        HStack(spacing: 12) {
            StatChip(title: "In", value: Formatters.money(summary.income), tint: AppTheme.income)
            StatChip(title: "Out", value: Formatters.money(summary.expenses), tint: AppTheme.expense)
        }
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 16)
    }

    private var spendingChart: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Where it went")
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(AppTheme.ink)

            Chart(breakdown, id: \.0.id) { item in
                SectorMark(
                    angle: .value("Spent", item.1),
                    innerRadius: .ratio(0.62),
                    angularInset: 1.5
                )
                .foregroundStyle(item.0.color)
                .cornerRadius(4)
            }
            .frame(height: 180)
            .chartLegend(.hidden)

            VStack(spacing: 10) {
                ForEach(breakdown.prefix(4), id: \.0.id) { item in
                    HStack {
                        Circle()
                            .fill(item.0.color)
                            .frame(width: 8, height: 8)
                        Text(item.0.name)
                            .font(.system(.subheadline, design: .rounded))
                            .foregroundStyle(AppTheme.ink)
                        Spacer()
                        Text(Formatters.money(item.1))
                            .font(.system(.subheadline, design: .rounded, weight: .semibold))
                            .foregroundStyle(AppTheme.inkMuted)
                    }
                }
            }
        }
        .padding(18)
        .background(AppTheme.surfaceElevated.opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }

    private var recentSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Recent")
                    .font(.system(.title3, design: .rounded, weight: .bold))
                    .foregroundStyle(AppTheme.ink)
                Spacer()
                Button("Add", action: onAdd)
                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                    .foregroundStyle(AppTheme.pine)
            }

            if recent.isEmpty {
                Text("No transactions yet. Add your first one.")
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(AppTheme.inkMuted)
                    .padding(.vertical, 20)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(recent.enumerated()), id: \.element.id) { index, transaction in
                        TransactionRow(transaction: transaction)
                        if index < recent.count - 1 {
                            Divider().opacity(0.35)
                        }
                    }
                }
                .padding(16)
                .background(AppTheme.surfaceElevated.opacity(0.9))
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
            }
        }
    }
}

private struct StatChip: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(.caption2, design: .rounded, weight: .bold))
                .foregroundStyle(tint)
                .tracking(0.8)
            Text(value)
                .font(.system(.title3, design: .rounded, weight: .bold))
                .foregroundStyle(AppTheme.ink)
                .minimumScaleFactor(0.8)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(AppTheme.surfaceElevated.opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}
