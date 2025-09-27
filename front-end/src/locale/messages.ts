export type LocaleCode = 'ko' | 'en' | 'ja';

export type TranslationKey =
    | 'header.title'
    | 'header.languageLabel'
    | 'header.languageKo'
    | 'header.languageEn'
    | 'header.languageJa'
    | 'header.languageAlpha'
    | 'chatbot.initialGreeting'
    | 'chatbot.pending'
    | 'chatbot.callSuggestion.title'
    | 'chatbot.callSuggestion.description'
    | 'chatbot.callSuggestion.button.callInProgress'
    | 'chatbot.callSuggestion.button.restart'
    | 'chatbot.callSuggestion.button.start'
    | 'chatbot.callSuggestion.note'
    | 'chatbot.toast.callStarted.title'
    | 'chatbot.toast.callStarted.description'
    | 'chatbot.toast.callFailed.title'
    | 'chatbot.toast.callFailed.description'
    | 'chatbot.toast.messageFailed.title'
    | 'chatbot.toast.messageFailed.description'
    | 'chatbot.input.placeholder'
    | 'chatbot.input.ariaLabel'
    | 'chatbot.button.sendAriaLabel'
    | 'chatbot.callButton.callInProgress'
    | 'chatbot.callButton.restart'
    | 'chatbot.callButton.start'
    | 'information.title'
    | 'information.error'
    | 'information.retry'
    | 'information.idle'
    | 'information.awaiting'
    | 'information.empty'
    | 'information.receivedAt'
    | 'information.previous'
    | 'information.next'
    | 'transcription.title'
    | 'transcription.scenarioBadge'
    | 'transcription.connecting'
    | 'transcription.dialing'
    | 'transcription.error'
    | 'transcription.retry'
    | 'transcription.waiting'
    | 'transcription.idle'
    | 'transcription.agentLabel'
    | 'transcription.userLabel'
    | 'transcription.callInitiateFailed'
    | 'transcription.unknownError'
    | 'transcription.dialingButton'
    | 'transcription.testCall'
    | 'transcription.twilioStatus'
    | 'transcription.callStatus'
    | 'transcription.callIdle'
    | 'transcription.elapsed'
    | 'transcription.errorCode'
    | 'transcription.waitingAnswer'
    | 'transcription.callSid'
    | 'transcription.dialError'
    | 'transcription.callError'
    | 'transcription.scenarioProgress'
    | 'transcription.scenarioStatus.complete'
    | 'transcription.scenarioStatus.inProgress'
    | 'transcription.scenarioToggle.scenario1'
    | 'transcription.scenarioToggle.scenario2'
    | 'transcription.scenarioToggle.scenario3'
    | 'transcription.status.queued'
    | 'transcription.status.initiated'
    | 'transcription.status.ringing'
    | 'transcription.status.in-progress'
    | 'transcription.status.answered'
    | 'transcription.status.completed'
    | 'transcription.status.busy'
    | 'transcription.status.failed'
    | 'transcription.status.no-answer'
    | 'transcription.status.canceled'
    | 'transcription.status.unknown'
    | 'transcription.noTargetWarning'
    | 'mapRoute.distance'
    | 'mapRoute.distancePrefix'
    | 'mapRoute.durationPrefix'
    | 'mapRoute.duration.minutes'
    | 'mapRoute.duration.hours'
    | 'mapRoute.duration.hoursMinutes'
    | 'mapRoute.businessListTitle'
    | 'mapRoute.error.missingKey'
    | 'mapRoute.error.loadFailed'
    | 'mapRoute.infoWindow.addressLabel'
    | 'mapRoute.infoWindow.phoneLabel'
    | 'chart.fishingYield.title'
    | 'chart.fishingYield.series.mahi'
    | 'chart.fishingYield.series.wahoo';

export const defaultLocale: LocaleCode = 'ko';

export const supportedLocales: Array<{ value: LocaleCode; label: string; flag?: string; isAlpha?: boolean }> = [
    { value: 'ko', label: '한국어', flag: '🇰🇷' },
    { value: 'en', label: 'English', flag: '🇺🇸' },
    { value: 'ja', label: '日本語', flag: '🇯🇵', isAlpha: true },
];

export const messages: Record<TranslationKey, Record<LocaleCode, string>> = {
    'header.title': {
        ko: '낚시하러 오시구룡~',
        en: 'Welcome to Guryongpo Fishing Planner',
        ja: '九龍浦釣りプランナーへようこそ',
    },
    'header.languageLabel': {
        ko: '언어',
        en: 'Language',
        ja: '言語',
    },
    'header.languageKo': {
        ko: '한국어',
        en: 'Korean',
        ja: '韓国語',
    },
    'header.languageEn': {
        ko: '영어',
        en: 'English',
        ja: '英語',
    },
    'header.languageJa': {
        ko: '일본어',
        en: 'Japanese',
        ja: '日本語',
    },
    'header.languageAlpha': {
        ko: '(알파)',
        en: '(Alpha)',
        ja: '(アルファ)',
    },
    'chatbot.initialGreeting': {
        ko: '안녕하세요! 무엇을 도와드릴까요?',
        en: 'Hello! How can I assist you today?',
        ja: 'こんにちは！本日はいかがいたしましょうか？',
    },
    'chatbot.pending': {
        ko: '생각하는 중…',
        en: 'Thinking…',
        ja: '考え中…',
    },
    'chatbot.callSuggestion.title': {
        ko: '예약 가능 여부를 확인해볼까요?',
        en: 'Ready to confirm availability?',
        ja: '空き状況を確認しましょうか？',
    },
    'chatbot.callSuggestion.description': {
        ko: '지금 바로 낚시점에 연결해서 통화 내용을 실시간으로 보여드릴 수 있어요. 준비되면 시작해 주세요.',
        en: 'I can connect with the charter shop and stream the conversation live. Start the call whenever you’re ready.',
        ja: '釣り船店に接続して通話内容をライブ配信できます。準備ができたら開始してください。',
    },
    'chatbot.callSuggestion.button.callInProgress': {
        ko: '통화 진행 중',
        en: 'Call in Progress',
        ja: '通話中',
    },
    'chatbot.callSuggestion.button.restart': {
        ko: '통화 다시 시작',
        en: 'Restart Call',
        ja: '通話を再開',
    },
    'chatbot.callSuggestion.button.start': {
        ko: '통화 시작',
        en: 'Start Call',
        ja: '通話開始',
    },
    'chatbot.callSuggestion.note': {
        ko: '통화가 시작되면 우측 패널에서 실시간 전사를 확인할 수 있어요.',
        en: 'Once the call begins, you can follow the live transcript on the right panel.',
        ja: '通話が始まると右側パネルでライブ文字起こしを確認できます。',
    },
    'chatbot.toast.callStarted.title': {
        ko: '통화를 시작했어요',
        en: 'Call started',
        ja: '通話を開始しました',
    },
    'chatbot.toast.callStarted.description': {
        ko: '낚시점과의 통화 내용이 실시간 전사로 전송됩니다.',
        en: 'Streaming live transcription from the charter call.',
        ja: '釣り店との通話内容がライブ文字起こしで表示されます。',
    },
    'chatbot.toast.callFailed.title': {
        ko: '통화를 시작하지 못했어요',
        en: 'Call failed',
        ja: '通話開始に失敗しました',
    },
    'chatbot.toast.callFailed.description': {
        ko: '통화 요청을 보내는 중 문제가 발생했습니다.',
        en: 'Failed to start the call.',
        ja: '通話の開始に問題が発生しました。',
    },
    'chatbot.toast.messageFailed.title': {
        ko: '메시지 전송 실패',
        en: 'Message failed',
        ja: 'メッセージ送信失敗',
    },
    'chatbot.toast.messageFailed.description': {
        ko: '챗봇 응답을 받아오지 못했습니다.',
        en: 'Failed to fetch agent response.',
        ja: 'チャットボットの応答を取得できませんでした。',
    },
    'chatbot.input.placeholder': {
        ko: '메시지를 입력하세요…',
        en: 'Type a message…',
        ja: 'メッセージを入力してください…',
    },
    'chatbot.input.ariaLabel': {
        ko: '메시지 입력란',
        en: 'Chat message input',
        ja: 'メッセージ入力欄',
    },
    'chatbot.button.sendAriaLabel': {
        ko: '메시지 전송',
        en: 'Send message',
        ja: 'メッセージを送信',
    },
    'chatbot.callButton.callInProgress': {
        ko: '통화 진행 중',
        en: 'Call in Progress',
        ja: '通話中',
    },
    'chatbot.callButton.restart': {
        ko: '통화 다시 시작',
        en: 'Restart Call',
        ja: '通話を再開',
    },
    'chatbot.callButton.start': {
        ko: '통화 시작',
        en: 'Start Call',
        ja: '通話開始',
    },
    'information.title': {
        ko: '구룡이가 모은 정보',
        en: 'Agent Tool Insights',
        ja: 'エージェントツールのインサイト',
    },
    'information.error': {
        ko: '전사 스트림을 불러오지 못했습니다.',
        en: 'Failed to load transcription stream.',
        ja: '文字起こしストリームを読み込めませんでした。',
    },
    'information.retry': {
        ko: '다시 시도',
        en: 'Retry',
        ja: '再試行',
    },
    'information.idle': {
        ko: '계획, 통화내용 등 각종 정보가 여기에 표시됩니다.',
        en: 'Start a call to collect live insights. Any agent tool results will appear here as they are produced.',
        ja: '通話を開始すると、ここにリアルタイムのインサイトが表示されます。',
    },
    'information.awaiting': {
        ko: '에이전트가 작업 중입니다. 첫 번째 도구 실행 결과가 도착하면 이곳에 표시돼요.',
        en: 'The agent is working. Tool results will appear here once the first tool completes.',
        ja: 'エージェントが処理中です。最初のツール結果が届くとここに表示されます。',
    },
    'information.empty': {
        ko: '아직 표시할 도구 결과가 없습니다.',
        en: 'No tool results are available yet for this session.',
        ja: 'このセッションにはまだツール結果がありません。',
    },
    'information.receivedAt': {
        ko: '{{time}} 수신',
        en: 'Received at {{time}}',
        ja: '{{time}} 受信',
    },
    'information.previous': {
        ko: '이전',
        en: 'Previous',
        ja: '前へ',
    },
    'information.next': {
        ko: '다음',
        en: 'Next',
        ja: '次へ',
    },
    'transcription.title': {
        ko: '실시간 통화 내역',
        en: 'Live Transcription',
        ja: 'ライブ通話文字起こし',
    },
    'transcription.scenarioBadge': {
        ko: '시나리오',
        en: 'Scenario',
        ja: 'シナリオ',
    },
    'transcription.connecting': {
        ko: '통화 서비스에 연결하는 중…',
        en: 'Connecting to call service…',
        ja: '通話サービスに接続中…',
    },
    'transcription.dialing': {
        ko: '낚시점에 전화 거는 중…',
        en: 'Dialing the charter…',
        ja: '釣り店に電話しています…',
    },
    'transcription.error': {
        ko: '전사 데이터를 가져오지 못했습니다.',
        en: 'Unable to fetch transcription.',
        ja: '文字起こしを取得できませんでした。',
    },
    'transcription.retry': {
        ko: '다시 시도',
        en: 'Retry',
        ja: '再試行',
    },
    'transcription.waiting': {
        ko: '상대방이 전화를 받을 때까지 기다리는 중입니다…',
        en: 'Waiting for the other party to pick up…',
        ja: '相手が電話に出るのを待っています…',
    },
    'transcription.idle': {
        ko: '통화를 시작하면 여기에서 실시간 대화를 볼 수 있어요.',
        en: 'Start a call to see the live conversation here.',
        ja: '通話を開始するとここでライブ会話を確認できます。',
    },
    'transcription.agentLabel': {
        ko: '에이전트',
        en: 'Agent',
        ja: 'エージェント',
    },
    'transcription.userLabel': {
        ko: '사용자',
        en: 'User',
        ja: 'ユーザー',
    },
    'transcription.callInitiateFailed': {
        ko: '통화 요청 실패',
        en: 'Call initiate failed',
        ja: '通話リクエストに失敗しました',
    },
    'transcription.unknownError': {
        ko: '알 수 없는 오류',
        en: 'Unknown error',
        ja: '不明なエラー',
    },
    'transcription.dialingButton': {
        ko: '전화 연결 중…',
        en: 'Dialing…',
        ja: '発信中…',
    },
    'transcription.testCall': {
        ko: '테스트 전화',
        en: 'Test Call',
        ja: 'テスト通話',
    },
    'transcription.twilioStatus': {
        ko: 'Twilio 상태',
        en: 'Twilio Status',
        ja: 'Twilioステータス',
    },
    'transcription.callStatus': {
        ko: '통화 상태',
        en: 'Call',
        ja: '通話',
    },
    'transcription.callIdle': {
        ko: '대기',
        en: 'idle',
        ja: '待機',
    },
    'transcription.elapsed': {
        ko: '경과',
        en: 'Elapsed',
        ja: '経過時間',
    },
    'transcription.errorCode': {
        ko: '오류 코드',
        en: 'Err',
        ja: 'エラー',
    },
    'transcription.waitingAnswer': {
        ko: '응답 대기 중…',
        en: 'Waiting answer…',
        ja: '応答を待っています…',
    },
    'transcription.callSid': {
        ko: '통화 SID',
        en: 'Call SID',
        ja: '通話SID',
    },
    'transcription.dialError': {
        ko: '통화 오류',
        en: 'Dial Error',
        ja: '発信エラー',
    },
    'transcription.callError': {
        ko: '통화 오류',
        en: 'Call Error',
        ja: '通話エラー',
    },
    'transcription.scenarioProgress': {
        ko: '{{current}}/{{total}}{{status}}',
        en: '{{current}}/{{total}}{{status}}',
        ja: '{{current}}/{{total}}{{status}}',
    },
    'transcription.scenarioStatus.complete': {
        ko: '(완료)',
        en: '(Done)',
        ja: '(完了)',
    },
    'transcription.scenarioStatus.inProgress': {
        ko: '(진행 중)',
        en: '(In progress)',
        ja: '(進行中)',
    },
    'transcription.scenarioToggle.scenario1': {
        ko: '시나리오 1',
        en: 'Scenario 1',
        ja: 'シナリオ 1',
    },
    'transcription.scenarioToggle.scenario2': {
        ko: '시나리오 2',
        en: 'Scenario 2',
        ja: 'シナリオ 2',
    },
    'transcription.scenarioToggle.scenario3': {
        ko: '시나리오 3',
        en: 'Scenario 3',
        ja: 'シナリオ 3',
    },
    'transcription.status.queued': {
        ko: '대기 중',
        en: 'Queued',
        ja: 'キュー待ち',
    },
    'transcription.status.initiated': {
        ko: '발신 준비',
        en: 'Initiated',
        ja: '発信準備',
    },
    'transcription.status.ringing': {
        ko: '벨 울림',
        en: 'Ringing',
        ja: '呼び出し中',
    },
    'transcription.status.in-progress': {
        ko: '통화 진행 중',
        en: 'In Progress',
        ja: '通話中',
    },
    'transcription.status.answered': {
        ko: '응답 완료',
        en: 'Answered',
        ja: '応答済み',
    },
    'transcription.status.completed': {
        ko: '통화 완료',
        en: 'Completed',
        ja: '通話完了',
    },
    'transcription.status.busy': {
        ko: '통화 중',
        en: 'Busy',
        ja: '話し中',
    },
    'transcription.status.failed': {
        ko: '실패',
        en: 'Failed',
        ja: '失敗',
    },
    'transcription.status.no-answer': {
        ko: '응답 없음',
        en: 'No Answer',
        ja: '応答なし',
    },
    'transcription.status.canceled': {
        ko: '취소됨',
        en: 'Canceled',
        ja: 'キャンセル済み',
    },
    'transcription.status.unknown': {
        ko: '알 수 없는 상태',
        en: 'Unknown status',
        ja: '不明な状態',
    },
    'transcription.noTargetWarning': {
        ko: '발신 대상이 설정되어 있지 않습니다.',
        en: 'No call target configured.',
        ja: '発信先が設定されていません。',
    },
    'mapRoute.distance': {
        ko: '{{value}}km',
        en: '{{value}} km',
        ja: '{{value}}km',
    },
    'mapRoute.distancePrefix': {
        ko: '거리',
        en: 'Distance',
        ja: '距離',
    },
    'mapRoute.durationPrefix': {
        ko: '예상 소요',
        en: 'Estimated time',
        ja: '所要時間',
    },
    'mapRoute.duration.minutes': {
        ko: '{{value}}분',
        en: '{{value}} min',
        ja: '{{value}}分',
    },
    'mapRoute.duration.hours': {
        ko: '{{value}}시간',
        en: '{{value}} hr',
        ja: '{{value}}時間',
    },
    'mapRoute.duration.hoursMinutes': {
        ko: '{{hours}}시간 {{minutes}}분',
        en: '{{hours}} hr {{minutes}} min',
        ja: '{{hours}}時間{{minutes}}分',
    },
    'mapRoute.businessListTitle': {
        ko: '주변 낚시점',
        en: 'Nearby fishing shops',
        ja: '周辺の釣具店',
    },
    'mapRoute.error.missingKey': {
        ko: '카카오 지도 API 키(NEXT_PUBLIC_KAKAO_MAP_KEY)가 설정되어 있지 않습니다.',
        en: 'Kakao Maps API key (NEXT_PUBLIC_KAKAO_MAP_KEY) is not configured.',
        ja: 'Kakao地図APIキー(NEXT_PUBLIC_KAKAO_MAP_KEY)が設定されていません。',
    },
    'mapRoute.error.loadFailed': {
        ko: '카카오 지도 SDK를 불러오지 못했습니다. 네트워크 상태를 확인하세요.',
        en: 'Unable to load the Kakao Maps SDK. Please check your network connection.',
        ja: 'Kakao地図SDKを読み込めませんでした。ネットワーク接続を確認してください。',
    },
    'mapRoute.infoWindow.addressLabel': {
        ko: '주소',
        en: 'Address',
        ja: '住所',
    },
    'mapRoute.infoWindow.phoneLabel': {
        ko: '전화',
        en: 'Phone',
        ja: '電話',
    },
    'chart.fishingYield.title': {
        ko: '월별 어획량 (파운드)',
        en: 'Monthly Fishing Yields (lbs)',
        ja: '月別漁獲量 (ポンド)',
    },
    'chart.fishingYield.series.mahi': {
        ko: '만새기 (Mahi-mahi)',
        en: 'Mahi-mahi',
        ja: 'シイラ',
    },
    'chart.fishingYield.series.wahoo': {
        ko: '와후 (Wahoo)',
        en: 'Wahoo',
        ja: 'カマスサワラ',
    },
};
