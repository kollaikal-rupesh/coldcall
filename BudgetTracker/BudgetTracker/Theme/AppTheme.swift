import SwiftUI

enum AppTheme {
    static let ink = Color(red: 0.11, green: 0.16, blue: 0.15)
    static let inkMuted = Color(red: 0.35, green: 0.42, blue: 0.40)
    static let surface = Color(red: 0.96, green: 0.97, blue: 0.95)
    static let surfaceElevated = Color.white
    static let pine = Color(red: 0.12, green: 0.38, blue: 0.32)
    static let pineSoft = Color(red: 0.22, green: 0.55, blue: 0.46)
    static let moss = Color(red: 0.55, green: 0.72, blue: 0.58)
    static let coral = Color(red: 0.86, green: 0.35, blue: 0.30)
    static let amber = Color(red: 0.89, green: 0.62, blue: 0.22)
    static let sky = Color(red: 0.30, green: 0.52, blue: 0.62)

    static let income = pineSoft
    static let expense = coral

    static var backgroundGradient: LinearGradient {
        LinearGradient(
            colors: [
                Color(red: 0.93, green: 0.96, blue: 0.94),
                Color(red: 0.97, green: 0.96, blue: 0.92),
                Color(red: 0.94, green: 0.95, blue: 0.97)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var heroGradient: LinearGradient {
        LinearGradient(
            colors: [pine, pineSoft],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

struct ScreenBackground: View {
    var body: some View {
        ZStack {
            AppTheme.backgroundGradient
            GeometryReader { geo in
                Circle()
                    .fill(AppTheme.moss.opacity(0.12))
                    .frame(width: geo.size.width * 0.7)
                    .blur(radius: 40)
                    .offset(x: -geo.size.width * 0.25, y: -40)
                Circle()
                    .fill(AppTheme.sky.opacity(0.10))
                    .frame(width: geo.size.width * 0.6)
                    .blur(radius: 50)
                    .offset(x: geo.size.width * 0.45, y: geo.size.height * 0.55)
            }
        }
        .ignoresSafeArea()
    }
}
