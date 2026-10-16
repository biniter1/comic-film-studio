interface PlaceholderPageProps {
  title: string;
  phase: string;
  description: string;
}

export function PlaceholderPage({ title, phase, description }: PlaceholderPageProps) {
  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">{title}</h1>
        <p className="text-gray-400 mt-1">{description}</p>
      </div>

      <div className="bg-surface border border-border rounded-lg p-8 text-center space-y-4">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-purple-900/30 text-purple-400 font-semibold text-lg">
          {phase}
        </div>
        <h3 className="text-lg font-medium text-gray-200">Sẽ có ở phase sau</h3>
        <p className="text-sm text-gray-400 max-w-md mx-auto">
          Màn hình này đang trong lộ trình phát triển theo đặc tả kỹ thuật <code>docs/SPEC.md</code>.
          Trong Phase 0, vui lòng sử dụng màn hình <strong>Job</strong> và <strong>Cài đặt</strong>.
        </p>
      </div>
    </div>
  );
}
