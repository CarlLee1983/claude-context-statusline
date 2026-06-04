import Foundation

enum StatusMenuLayout {
    static let width: CGFloat = 320
    static let compactHeight: CGFloat = 82
    static let maximumProviderListHeight: CGFloat = 520
    static let maximumHostingHeight: CGFloat = 580

    static func hostingHeight(measuredHeight: CGFloat) -> CGFloat {
        guard measuredHeight.isFinite, measuredHeight > 0 else {
            return compactHeight
        }
        return min(max(measuredHeight, compactHeight), maximumHostingHeight)
    }
}
