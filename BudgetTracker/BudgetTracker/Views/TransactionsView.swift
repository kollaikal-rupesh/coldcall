import SwiftUI
import SwiftData

struct TransactionsView: View {
    @Environment(\.modelContext) private var modelContext
    @Query(sort: \Transaction.date, order: .reverse) private var transactions: [Transaction]
    @State private var filter: TransactionKind?
    @State private var showAdd = false
    @State private var search = ""

    private var filtered: [Transaction] {
        transactions.filter { transaction in
            let matchesKind = filter == nil || transaction.kind == filter
            let matchesSearch = search.isEmpty
                || transaction.title.localizedCaseInsensitiveContains(search)
                || (transaction.category?.name.localizedCaseInsensitiveContains(search) ?? false)
            return matchesKind && matchesSearch
        }
    }

    private var grouped: [(Date, [Transaction])] {
        BudgetMath.groupedByDay(filtered)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ScreenBackground()

                VStack(spacing: 0) {
                    filterBar
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                        .padding(.bottom, 12)

                    if filtered.isEmpty {
                        ContentUnavailableView(
                            "No activity",
                            systemImage: "tray",
                            description: Text("Try another filter or add a transaction.")
                        )
                        .foregroundStyle(AppTheme.inkMuted)
                    } else {
                        List {
                            ForEach(grouped, id: \.0) { day, items in
                                Section {
                                    ForEach(items) { transaction in
                                        TransactionRow(transaction: transaction)
                                            .listRowBackground(AppTheme.surfaceElevated.opacity(0.88))
                                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                                Button(role: .destructive) {
                                                    modelContext.delete(transaction)
                                                } label: {
                                                    Label("Delete", systemImage: "trash")
                                                }
                                            }
                                    }
                                } header: {
                                    Text(Formatters.shortDate.string(from: day))
                                        .font(.system(.caption, design: .rounded, weight: .semibold))
                                        .foregroundStyle(AppTheme.inkMuted)
                                        .textCase(nil)
                                }
                            }
                        }
                        .scrollContentBackground(.hidden)
                        .listStyle(.insetGrouped)
                    }
                }
            }
            .navigationTitle("Activity")
            .navigationBarTitleDisplayMode(.large)
            .searchable(text: $search, prompt: "Search transactions")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showAdd = true
                    } label: {
                        Image(systemName: "plus")
                            .fontWeight(.semibold)
                    }
                }
            }
            .sheet(isPresented: $showAdd) {
                AddTransactionView()
            }
        }
    }

    private var filterBar: some View {
        HStack(spacing: 8) {
            FilterPill(title: "All", selected: filter == nil) { filter = nil }
            FilterPill(title: "Income", selected: filter == .income) { filter = .income }
            FilterPill(title: "Expense", selected: filter == .expense) { filter = .expense }
            Spacer()
        }
    }
}

private struct FilterPill: View {
    let title: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(.subheadline, design: .rounded, weight: .semibold))
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(selected ? AppTheme.pine : AppTheme.surfaceElevated.opacity(0.9))
                .foregroundStyle(selected ? Color.white : AppTheme.ink)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .animation(.easeInOut(duration: 0.2), value: selected)
    }
}
