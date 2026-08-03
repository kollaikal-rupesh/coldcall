import SwiftUI

struct RootTabView: View {
    @State private var selectedTab = 0
    @State private var showAdd = false

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView(onAdd: { showAdd = true })
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(0)

            TransactionsView()
                .tabItem {
                    Label("Activity", systemImage: "list.bullet.rectangle")
                }
                .tag(1)

            BudgetsView()
                .tabItem {
                    Label("Budgets", systemImage: "chart.pie.fill")
                }
                .tag(2)
        }
        .tint(AppTheme.pine)
        .sheet(isPresented: $showAdd) {
            AddTransactionView()
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }
}

#Preview {
    RootTabView()
        .modelContainer(for: [Transaction.self, BudgetCategory.self, CategoryBudget.self], inMemory: true)
}
