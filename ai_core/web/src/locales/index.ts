import { createI18n } from 'vue-i18n'
import zh from './zh'
import en from './en'

const savedLocale = localStorage.getItem('arisu-locale') || 'zh'

const i18n = createI18n({
  legacy: false,
  locale: savedLocale,
  fallbackLocale: 'zh',
  messages: { zh, en },
})

export function setLocale(locale: 'zh' | 'en') {
  i18n.global.locale.value = locale
  localStorage.setItem('arisu-locale', locale)
}

export function getLocale(): string {
  return i18n.global.locale.value
}

export default i18n
